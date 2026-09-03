"""话轮收尾 STT（WS mixin）：PCM 超限 / 回采判定 / 识别失败与入轮。

拆自 :mod:`...turn_coordinator`。PCM 与浏览器文本两条路径共用同一份
``transcribe_utterance_result`` 绑定（本模块顶层名字，测试
patch ``interview_service.realtime.turn.stt_finish.transcribe_utterance_result``），
最后统一 ``_pick_stt_text`` → 回采判定 → ``_process_user_text``。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.realtime.core.events import TurnState
from shared.capabilities.voice.stt import transcribe_utterance_result
from interview_service.realtime.voice.pipeline import _is_echo_of_assistant, _pick_stt_text

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

_AUDIO_BUFFER_MAX_BYTES: int = 5 * 1024 * 1024


class TurnSttFinishMixin:
    """候选人语音回合收尾：STT、回采、失败计数；成功清零后入轮。"""

    ctx: "ConnectionContext"

    async def _run_user_turn_end(
        self,
        data: dict[str, Any],
    ) -> None:
        epoch = self._begin_user_turn()
        if epoch is None:
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                return
            self.rebind_runtime_session(session)
            await self._on_user_turn_end(data, db, session)
        except Exception:
            logger.exception("user_turn_end 失败 sid=%s", self.ctx.session_id)
            try:
                if epoch == self.ctx.stream_epoch:
                    await self.set_turn(TurnState.USER_SPEAKING)
            except Exception:
                logger.debug(
                    "user_turn_end 恢复 USER_SPEAKING 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            self._end_user_turn(epoch)
            try:
                db.close()
            except Exception:
                logger.debug(
                    "user_turn_end DB close 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

    async def _on_user_turn_end(
        self, data: dict[str, Any], db: Session, session: InterviewSession
    ) -> None:
        if self.ctx.turn_state == TurnState.PROCESSING:
            return
        if self.ctx.turn_state == TurnState.AI_SPEAKING:
            logger.info("忽略 AI_SPEAKING 期间的 user_turn_end sid=%s", self.ctx.session_id)
            return
        await self.set_turn(TurnState.PROCESSING)

        browser_text = (data.get("text") or "").strip()
        pcm_b64 = data.get("pcm") or data.get("data") or ""
        if isinstance(pcm_b64, str) and len(pcm_b64) > _AUDIO_BUFFER_MAX_BYTES:
            logger.warning(
                "user_turn_end pcm 超限 sid=%s len=%d",
                self.ctx.session_id,
                len(pcm_b64),
            )
            await self.send(
                "error",
                message="音频过大，请分段说话或改用文字输入",
                code="A0004",
            )
            await self.set_turn(TurnState.USER_SPEAKING)
            return

        asr_text = ""
        if pcm_b64:
            raw_sr = data.get("sample_rate") or 16000
            try:
                sample_rate = int(raw_sr)
            except (TypeError, ValueError):
                sample_rate = 16000
            if sample_rate < 8000 or sample_rate > 96000:
                sample_rate = 16000
            stt_result = await transcribe_utterance_result(
                pcm_b64,
                sample_rate=sample_rate,
                creds=self.ctx.stt_creds,
            )
            asr_text = stt_result.text
            if stt_result.fallback:
                await self.send(
                    "info",
                    message=(
                        f"识别已回退到 {stt_result.provider}"
                        + (
                            f"（原配置 {stt_result.requested_provider}）"
                            if stt_result.requested_provider
                            else ""
                        )
                    ),
                    fallback=True,
                    provider=stt_result.provider,
                    requested_provider=stt_result.requested_provider,
                )
        elif self.ctx.audio_buffer and not browser_text:
            pcm = "".join(self.ctx.audio_buffer)
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0
            if len(pcm) > _AUDIO_BUFFER_MAX_BYTES:
                await self.send(
                    "error",
                    message="音频过大，请分段说话或改用文字输入",
                    code="A0004",
                )
                await self.set_turn(TurnState.USER_SPEAKING)
                return
            stt_result = await transcribe_utterance_result(
                pcm,
                creds=self.ctx.stt_creds,
            )
            asr_text = stt_result.text
            if stt_result.fallback:
                await self.send(
                    "info",
                    message=f"识别已回退到 {stt_result.provider}",
                    fallback=True,
                    provider=stt_result.provider,
                )
        elif self.ctx.audio_buffer:
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0

        text = _pick_stt_text(browser_text, asr_text)
        if text:
            if await self._reject_probable_echo(text):
                return
            await self.send("stt_final", text=text)
        else:
            self.ctx.stt_fail_streak += 1
            await self.send(
                "error",
                message="未能识别语音内容，请重新说话或手动输入",
                code="C2001",
                retryable=True,
            )
            await self.set_turn(TurnState.USER_SPEAKING)
            return

        self.ctx.stt_fail_streak = 0
        await self._process_user_text(text, data, db, session)

    def _last_assistant_content(self) -> str:
        """消息历史中最近一条面试官发言（回采判定锚点；兼容 dict/ORM 形态）。"""
        if not (self.ctx.agent and self.ctx.agent.messages):
            return ""
        for m in reversed(self.ctx.agent.messages):
            role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
            content = getattr(m, "content", None) or (
                m.get("content") if isinstance(m, dict) else None
            )
            if role == "assistant" and content:
                return str(content)
        return ""

    async def _reject_probable_echo(self, text: str) -> bool:
        """扬声器回采判定：命中则提示重答并恢复开麦，返回 True（调用方终止入轮）。"""
        last_assistant = self._last_assistant_content()
        if not last_assistant or not _is_echo_of_assistant(text, last_assistant):
            return False
        logger.warning(
            "丢弃疑似回采 sid=%s text=%s",
            self.ctx.session_id,
            text[:80],
        )
        await self.send(
            "error",
            message="检测到可能误采了面试官声音，请再说一遍或打字作答",
            code="C2001",
            retryable=True,
        )
        await self.set_turn(TurnState.USER_SPEAKING)
        return True


__all__ = ["TurnSttFinishMixin", "_AUDIO_BUFFER_MAX_BYTES"]
