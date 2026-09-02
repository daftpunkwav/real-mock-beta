"""静默追问编排（WS mixin）：触发条件 + 追问下发 + 并入历史。

拟真追问的 LLM 生成见 :mod:`silence_probe`（本模块不复制生成逻辑）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from shared.database import SessionLocal
from interview_service.realtime.core.events import TurnState

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class SilenceNudgeMixin:
    """沉默追问编排；依赖 ctx 字段 + _generate_silence_probe（SilenceProbeMixin）。"""

    ctx: "ConnectionContext"

    async def _on_silence_nudge(self) -> None:
        """沉默拟真追问：由思考 LLM 结合当前问题/追问预案/沉默次数实时生成。

        同一问题最多追问 2 次（第 1 次鼓励开口，第 2 次直接给提示）；
        LLM 失败回退本地模板；追问文本并入上一条 assistant 发言，
        保持消息角色交替（Anthropic 协议要求）。
        """
        if self.ctx.turn_state != TurnState.USER_SPEAKING:
            return
        now = asyncio.get_event_loop().time()
        if self.ctx.mic_opened_at and now - self.ctx.mic_opened_at < self.ctx.nudge_grace_sec:
            return
        cooldown = self.ctx.nudge_cooldown_sec
        if self.ctx.stt_fail_streak >= 2:
            cooldown = 45.0
        if now - self.ctx.last_nudge_at < cooldown:
            return
        self.ctx.last_nudge_at = now
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                return
            question = self._last_assistant_text()
            if question != self.ctx.silence_probe_question:
                self.ctx.silence_probe_question = question
                self.ctx.silence_probe_seq = 0
            if self.ctx.silence_probe_seq >= 2:
                return
            self.ctx.silence_probe_seq += 1

            state = getattr(self.ctx.agent, "agent_state", {}) or {}
            probe_hint = str(state.get("last_probe") or "")
            silent_sec = int(now - self.ctx.mic_opened_at) if self.ctx.mic_opened_at else 0

            probe_text = await self._generate_silence_probe(
                question=question,
                probe_hint=probe_hint,
                attempt=self.ctx.silence_probe_seq,
                silent_sec=silent_sec,
            )
            if not probe_text or probe_text == self.ctx.last_silence_probe:
                probe_text = self.ctx.orchestrator.build_silence_nudge(
                    session.personality,
                    session.strictness,
                    phase=session.current_phase,
                )
            self.ctx.last_silence_probe = probe_text

            await self.set_turn(TurnState.PROCESSING)
            await self.send(
                "silence_nudge",
                content=probe_text,
                seq=self.ctx.silence_probe_seq,
            )
            self._begin_playback_wait()
            await self._speak_one(probe_text)
            self._append_to_last_assistant(probe_text)
            await self._open_mic_after_playback()
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "silence_nudge DB close 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

    def _last_assistant_text(self) -> str:
        """消息历史中最近一条面试官发言（拟真追问的上下文锚点）。"""
        if not self.ctx.agent:
            return ""
        for m in reversed(self.ctx.agent.messages):
            if m.get("role") == "assistant":
                return str(m.get("content") or "")
        return ""

    def _append_to_last_assistant(self, text: str) -> None:
        """把追问并入最近一条 assistant 发言，避免消息历史出现连续 assistant。"""
        if not self.ctx.agent or not text:
            return
        for m in reversed(self.ctx.agent.messages):
            if m.get("role") == "assistant":
                content = str(m.get("content") or "")
                m["content"] = f"{content}\n{text}" if content else text
                return


__all__ = ["SilenceNudgeMixin"]
