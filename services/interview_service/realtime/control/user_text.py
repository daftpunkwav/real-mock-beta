"""用户文本入轮（WS mixin）：候选人文字进回合主流程。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.realtime.events import TurnState
from interview_service.services.interview.events import EventKind

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext


class UserTextControlMixin:
    """候选人文本入轮；依赖 ctx.runner + turn_streaming 消费链。"""

    ctx: "ConnectionContext"

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


__all__ = ["UserTextControlMixin"]
