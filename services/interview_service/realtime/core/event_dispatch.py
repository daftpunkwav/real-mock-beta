"""StreamEvent 分发（WS mixin）：把 runner 事件转成 WS 消息。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from interview_service.services.interview.agent_text import strip_markers
from interview_service.services.interview.events import EventKind, StreamEvent

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext


class EventDispatchMixin:
    """StreamEvent → WS 消息分发；依赖 ctx.send。"""

    ctx: "ConnectionContext"

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


__all__ = ["EventDispatchMixin"]
