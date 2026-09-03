"""打断副作用（WS mixin）：候选人打断计数与 TTS 清空。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.realtime.core.events import TurnState

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class InterruptControlMixin:
    """候选人打断处理；依赖 ctx 状态字段 + send / set_turn / _load_session。"""

    ctx: "ConnectionContext"

    def _persist_interrupt_stats(self, session: InterviewSession, db: Session) -> None:
        """把打断计数并入 agent 内存态后落库（单一真相，防回合 save_state 覆盖回退）。"""
        try:
            state: dict = {}
            if self.ctx.agent is not None:
                state = dict(self.ctx.agent.agent_state)
            elif session.agent_state:
                loaded = json.loads(session.agent_state)
                state = loaded if isinstance(loaded, dict) else {}
            state["candidate_interrupts"] = self.ctx.candidate_interrupts
            state["ai_interrupts"] = self.ctx.ai_interrupts
            if self.ctx.agent is not None:
                # 内存态与库同步，后续回合 save_state 序列化时计数不丢
                self.ctx.agent.agent_state["candidate_interrupts"] = self.ctx.candidate_interrupts
                self.ctx.agent.agent_state["ai_interrupts"] = self.ctx.ai_interrupts
            session.agent_state = json.dumps(state, ensure_ascii=False)
            db.add(session)
            db.commit()
        except Exception:
            logger.exception("持久化打断统计失败 sid=%s", self.ctx.session_id)
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "打断统计 rollback 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

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
                logger.debug(
                    "打断统计 DB close 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        await self.set_turn(TurnState.USER_SPEAKING)
        logger.info(
            "候选人打断 sid=%s count=%s epoch=%s",
            self.ctx.session_id,
            self.ctx.candidate_interrupts,
            self.ctx.stream_epoch,
        )


__all__ = ["InterruptControlMixin"]
