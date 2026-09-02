"""WebSocket 面试会话处理器（组装壳）。

子包职责见各 mixin；本模块仅聚合 stack + dispatcher + report_scheduler。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from interview_service.realtime.core.context import ConnectionContext
from interview_service.realtime.core.message_dispatcher import (
    AUDIO_BUFFER_MAX_BYTES as _AUDIO_BUFFER_MAX_BYTES,
    MessageDispatcherMixin,
)
from interview_service.realtime.report_scheduler import ReportSchedulerMixin
from interview_service.realtime.core.session_registry import (
    claim_session_connection,
    get_ws_connection_registry,
    release_session_connection,
    reset_session_registry_for_tests,
    reset_ws_connection_registry,
    active_handlers_for_tests,
)
from interview_service.realtime.stacks.connection_stack import ConnectionStackMixin
from interview_service.realtime.stacks.media_stack import MediaStackMixin
from interview_service.realtime.stacks.turn_stack import TurnStackMixin
from interview_service.realtime.turn.streaming import _IMAGE_BASE64_MAX_LEN
from interview_service.realtime.voice.tts_queue import _SentenceTTSQueue
from interview_service.models import InterviewSession
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody
from shared.config import get_settings


logger = logging.getLogger(__name__)


class InterviewWSHandler(
    ConnectionStackMixin,
    MessageDispatcherMixin,
    TurnStackMixin,
    MediaStackMixin,
    ReportSchedulerMixin,
):
    """实时面试 WebSocket 会话 façade。"""

    def __init__(
        self,
        websocket: WebSocket,
        session_id: int,
        *,
        access_token: str | None = None,
        ws_subprotocol: str | None = None,
    ) -> None:
        cfg = get_settings()
        self.ctx = ConnectionContext(
            ws=websocket,
            session_id=session_id,
            client_access_token=(access_token or "").strip(),
            ws_subprotocol=ws_subprotocol,
            tts_voice=cfg.tts_voice,
            session_prosody=VoiceProsody(voice=cfg.tts_voice),
            whisper_model=cfg.whisper_model,
            nudge_cooldown_sec=float(max(5, int(getattr(cfg, "silence_nudge_seconds", 25) or 25))),
            tts_queue=_SentenceTTSQueue(),
        )

    @property
    def session_id(self) -> int:
        return self.ctx.session_id

    @property
    def ws(self) -> WebSocket:
        return self.ctx.ws

    @property
    def _superseded(self) -> bool:
        return self.ctx.superseded

    @_superseded.setter
    def _superseded(self, value: bool) -> None:
        self.ctx.superseded = value

    @property
    def lease_token(self) -> str:
        return self.ctx.lease_token

    def _spawn(self, coro) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self.ctx.bg_tasks.add(task)

        def _done(t: asyncio.Task[Any]) -> None:
            self.ctx.bg_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.exception("WS 后台任务异常 sid=%s: %s", self.ctx.session_id, exc)

        task.add_done_callback(_done)
        return task

    async def _cancel_bg_tasks(self) -> None:
        tasks = list(self.ctx.bg_tasks)
        if self.ctx.report_task is not None and not self.ctx.report_task.done():
            tasks.append(self.ctx.report_task)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.ctx.bg_tasks.clear()
        self.ctx.report_task = None

    def _load_session(self, db: Session) -> InterviewSession | None:
        return (
            db.query(InterviewSession)
            .filter(InterviewSession.id == self.ctx.session_id)
            .first()
        )


__all__ = [
    "InterviewWSHandler",
    "_AUDIO_BUFFER_MAX_BYTES",
    "_IMAGE_BASE64_MAX_LEN",
    "claim_session_connection",
    "get_ws_connection_registry",
    "release_session_connection",
    "reset_session_registry_for_tests",
    "reset_ws_connection_registry",
    "active_handlers_for_tests",
]
