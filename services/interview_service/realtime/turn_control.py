"""话轮副作用：打断、收尾、静默追问、事件分发（WS mixin）。

拟真追问的 LLM 生成见 :mod:`silence_probe`。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from shared.core.constants import SessionStatus
from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.realtime.events import TurnState
from interview_service.realtime.silence_probe import SilenceProbeMixin
from interview_service.services.interview.agent_text import strip_markers, strip_think_blocks
from interview_service.services.interview.events import EventKind, StreamEvent

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)


class TurnControlMixin(SilenceProbeMixin):
    """话轮副作用；依赖 ctx 中的状态字段 + 继承的方法。"""

    ctx: "ConnectionContext"

    def _persist_interrupt_stats(self, session: InterviewSession, db: Session) -> None:
        """把打断计数写入 agent_state，供报告礼貌分使用。"""
        try:
            state = json.loads(session.agent_state or "{}")
            if not isinstance(state, dict):
                state = {}
            state["candidate_interrupts"] = self.ctx.candidate_interrupts
            state["ai_interrupts"] = self.ctx.ai_interrupts
            session.agent_state = json.dumps(state, ensure_ascii=False)
            db.add(session)
            db.commit()
        except Exception:
            logger.exception("持久化打断统计失败 sid=%s", self.ctx.session_id)
            try:
                db.rollback()
            except Exception:
                pass

    async def _on_candidate_barge_in(self) -> None:
        """候选人打断面试官播报：清空 TTS、放开话轮。"""
        if self.ctx.turn_state not in (TurnState.AI_SPEAKING, TurnState.PROCESSING):
            return
        self.ctx.candidate_interrupts += 1
        self.ctx.stream_epoch += 1
        self.ctx.playback_generation += 1
        self.ctx.awaiting_playback_gen = self.ctx.playback_generation
        await self.ctx.tts_queue.clear()
        self.ctx.tts_sent_this_turn = False
        self.ctx.playback_done.set()
        self.ctx.audio_buffer = []
        self.ctx.audio_buffer_bytes = 0
        await self.send(
            "tts_interrupted",
            reason="candidate_barge",
            candidate_interrupts=self.ctx.candidate_interrupts,
            playback_generation=self.ctx.awaiting_playback_gen,
        )
        db = SessionLocal()
        try:
            try:
                session = self._load_session(db)
                if session:
                    self._persist_interrupt_stats(session, db)
            except Exception:
                logger.exception("打断统计读取失败 sid=%s", self.ctx.session_id)
        finally:
            try:
                db.close()
            except Exception:
                pass
        await self.set_turn(TurnState.USER_SPEAKING)
        logger.info(
            "候选人打断 sid=%s count=%s epoch=%s",
            self.ctx.session_id,
            self.ctx.candidate_interrupts,
            self.ctx.stream_epoch,
        )

    async def _process_user_text(
        self, text: str, data: dict[str, Any], db: Session, session: InterviewSession
    ) -> None:
        assert self.ctx.runner is not None
        start_epoch = self.ctx.stream_epoch
        await self.set_turn(TurnState.PROCESSING)
        await self.set_turn(TurnState.AI_SPEAKING)

        last = await self._stream_events_with_tts(
            self._consume_runner_turn(text, data, db),
            db=db,
            session=session,
            auto_hint=True,
        )
        if start_epoch != self.ctx.stream_epoch:
            return
        if self.ctx.turn_state == TurnState.USER_SPEAKING:
            return
        if last is None or last.kind == EventKind.ERROR:
            await self._open_mic_after_playback()
            return
        if last.is_complete:
            await self.set_turn(TurnState.IDLE)
            self._schedule_report_generation()
            self._spawn(self._wait_client_playback())
        else:
            await self._open_mic_after_playback()

    async def _on_request_finish(self) -> None:
        """候选人主动结束：流式口头致谢与评价，报告异步生成。"""
        if self.ctx.closing:
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                await self.send(
                    "error",
                    message="面试会话不存在",
                    code="A2001",
                )
                return
            if session.status == SessionStatus.COMPLETED.value:
                await self.send(
                    "assistant_done",
                    content="面试已结束，正在生成报告。",
                    phase=session.current_phase or "summary",
                    is_complete=True,
                    emotion="smile",
                )
                self._schedule_report_generation()
                return
            if self.ctx.runner is None or self.ctx.llm is None:
                await self.send(
                    "error",
                    message="面试引擎未就绪，无法收尾",
                    code="A0006",
                )
                return

            self.ctx.closing = True
            await self.set_turn(TurnState.PROCESSING)
            await self.set_turn(TurnState.AI_SPEAKING)
            last = await self._stream_events_with_tts(
                self.ctx.runner.stream_closing(db),
                db=db,
                session=session,
                auto_hint=False,
            )
            if last is None or last.kind == EventKind.ERROR:
                self.ctx.closing = False
                await self._open_mic_after_playback()
                await self.send(
                    "error",
                    message="收尾发言失败，请重试「结束面试」或检查 LLM 配置",
                    code="C0001",
                    retryable=True,
                )
                return

            await self.set_turn(TurnState.IDLE)
            self._schedule_report_generation()
            self._spawn(self._wait_client_playback())
        finally:
            try:
                db.close()
            except Exception:
                pass

    async def _dispatch_event(self, event: StreamEvent) -> None:
        if event.kind == EventKind.TOKEN:
            await self.send("assistant_token", token=event.token)
        elif event.kind == EventKind.TURN_COMPLETE:
            if event.phase_id:
                await self.send("phase_changed", phase=event.phase_id)
            await self.send(
                "assistant_done",
                content=strip_markers(event.content or ""),
                phase=event.phase_id,
                is_complete=event.is_complete,
                emotion=event.emotion,
            )
        elif event.kind == EventKind.ERROR:
            await self.send(
                "error",
                message=event.error,
                code=event.error_code or "C0001",
                retryable=event.error_retryable,
            )

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
                pass

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
