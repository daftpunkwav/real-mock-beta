"""主动收尾（WS mixin）：候选人 request_finish 的流式致谢与报告调度。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared.core.constants import SessionStatus
from shared.database import SessionLocal
from interview_service.realtime.core.events import TurnState
from interview_service.services.interview.events import EventKind

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class FinishControlMixin:
    """候选人主动结束；依赖 ctx.runner/llm + 报告调度链。"""

    ctx: "ConnectionContext"

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
                logger.debug(
                    "request_finish DB close 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )


__all__ = ["FinishControlMixin"]
