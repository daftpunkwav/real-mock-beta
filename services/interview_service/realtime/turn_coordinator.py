"""回合协调（WS mixin）：话轮锁、候选人回合；流式/副作用委托子 mixin。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.realtime.events import TurnState
from interview_service.realtime.turn_control import TurnControlMixin
from interview_service.realtime.turn_streaming import TurnStreamingMixin, _IMAGE_BASE64_MAX_LEN
from interview_service.realtime.voice_pipeline import _is_echo_of_assistant, _pick_stt_text
from shared.capabilities.voice.stt import transcribe_utterance_result  # noqa: F401 — 测试 patch 目标

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)

_AUDIO_BUFFER_MAX_BYTES: int = 5 * 1024 * 1024

__all__ = [
    "TurnCoordinatorMixin",
    "_AUDIO_BUFFER_MAX_BYTES",
    "_IMAGE_BASE64_MAX_LEN",
]


class TurnCoordinatorMixin(TurnStreamingMixin, TurnControlMixin):
    """候选人回合入口；组合流式消费与打断/收尾副作用。"""

    ctx: "ConnectionContext"

    def _can_start_user_turn(self) -> bool:
        """是否允许启动新的候选人回合（含打断后接棒）。"""
        if self.ctx.closing:
            return False
        if not self.ctx.turn_busy:
            return True
        return self.ctx.busy_epoch != self.ctx.stream_epoch

    def _begin_user_turn(self) -> int | None:
        """占用回合锁并绑定当前 epoch；不可启动时返回 None。"""
        if not self._can_start_user_turn():
            return None
        epoch = self.ctx.stream_epoch
        self.ctx.turn_busy = True
        self.ctx.busy_epoch = epoch
        return epoch

    def _end_user_turn(self, epoch: int) -> None:
        """仅当仍是本回合占用时释放锁。"""
        if self.ctx.busy_epoch == epoch:
            self.ctx.turn_busy = False

    async def _run_user_text(
        self,
        text: str,
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
            await self.set_turn(TurnState.PROCESSING)
            await self.send("stt_final", text=text)
            await self._process_user_text(text, data, db, session)
        except Exception:
            logger.exception("user_text 回合失败 sid=%s", self.ctx.session_id)
            try:
                if epoch == self.ctx.stream_epoch:
                    await self.set_turn(TurnState.USER_SPEAKING)
            except Exception:
                pass
        finally:
            self._end_user_turn(epoch)
            try:
                db.close()
            except Exception:
                pass

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
            await self._on_user_turn_end(data, db, session)
        except Exception:
            logger.exception("user_turn_end 失败 sid=%s", self.ctx.session_id)
            try:
                if epoch == self.ctx.stream_epoch:
                    await self.set_turn(TurnState.USER_SPEAKING)
            except Exception:
                pass
        finally:
            self._end_user_turn(epoch)
            try:
                db.close()
            except Exception:
                pass

    def _mark_tts_sent(self) -> None:
        self.ctx.tts_sent_this_turn = True

    def _begin_playback_wait(self) -> None:
        """新回合开始：提升世代并清空完成信号。"""
        self.ctx.playback_generation += 1
        self.ctx.awaiting_playback_gen = self.ctx.playback_generation
        self.ctx.tts_sent_this_turn = False
        self.ctx.playback_done.clear()

    async def _wait_client_playback(self) -> None:
        """若本回合发过 TTS，则等待客户端 tts_playback_done（或超时）。"""
        if not self.ctx.tts_sent_this_turn:
            return
        wait_gen = self.ctx.awaiting_playback_gen
        if not self.ctx.playback_done.is_set():
            try:
                await asyncio.wait_for(
                    self.ctx.playback_done.wait(),
                    timeout=self.ctx.playback_wait_timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "tts_playback_done 超时 sid=%s gen=%s，继续",
                    self.ctx.session_id,
                    wait_gen,
                )
        await asyncio.sleep(0.15)
        if self.ctx.awaiting_playback_gen == wait_gen:
            self.ctx.tts_sent_this_turn = False
            self.ctx.playback_done.clear()

    async def _open_mic_after_playback(self) -> None:
        """服务端合成发完后，等客户端播完（或超时）再切 USER_SPEAKING，防回采。"""
        wait_epoch = self.ctx.stream_epoch
        await self._wait_client_playback()
        if wait_epoch != self.ctx.stream_epoch:
            return
        if self.ctx.turn_state == TurnState.USER_SPEAKING:
            return
        await self.set_turn(TurnState.USER_SPEAKING)

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
            last_assistant = ""
            if self.ctx.agent and self.ctx.agent.messages:
                for m in reversed(self.ctx.agent.messages):
                    role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
                    content = getattr(m, "content", None) or (
                        m.get("content") if isinstance(m, dict) else None
                    )
                    if role == "assistant" and content:
                        last_assistant = str(content)
                        break
            if last_assistant and _is_echo_of_assistant(text, last_assistant):
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
