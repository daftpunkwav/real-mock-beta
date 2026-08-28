"""WebSocket 面试会话处理器（façade）。

具体职责拆到：

- :mod:`connection_lifecycle` — 握手 / 心跳 / 分发
- :mod:`turn_coordinator` — 话轮与候选人回合
- :mod:`voice_pipeline` — STT 选择与 TTS 队列
- :mod:`hint_service` — 参考提纲
- :mod:`report_scheduler` — 后台报告

本模块保留对外 API 与测试兼容 re-export。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from interview_service.realtime.context import ConnectionContext
from interview_service.realtime.connection_lifecycle import ConnectionLifecycleMixin
from interview_service.realtime.events import TurnState
from interview_service.realtime.hint_service import HintServiceMixin
from interview_service.realtime.report_scheduler import ReportSchedulerMixin
from interview_service.realtime.session_registry import (
    _active_handlers,  # noqa: F401 — 测试仍通过 ws_handler 访问
    claim_session_connection,
    release_session_connection,
    reset_session_registry_for_tests,
)
from interview_service.realtime.turn_coordinator import (
    TurnCoordinatorMixin,
    _AUDIO_BUFFER_MAX_BYTES,
    _IMAGE_BASE64_MAX_LEN,
)
from interview_service.realtime.voice_pipeline import (
    VoicePipelineMixin,
    _SentenceTTSQueue,
    _is_echo_of_assistant,
    _latin_letter_ratio,
    _normalize_echo_text,
    _pick_stt_text,
    _should_skip_whisper,
)
from interview_service.models import InterviewSession
from interview_service.services.interview.agent import strip_markers
from shared.capabilities.voice.stt import SttCredentials, SttResult, transcribe_utterance  # noqa: F401
from shared.capabilities.voice.tts import TtsCredentials, synthesize_speech  # noqa: F401 — 测试 patch
from shared.capabilities.voice.tts.voice_resolve import VoiceProsody
from shared.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

# 兼容测试 / 外部 import
_HEARTBEAT_TIMEOUT_SEC: float = 30.0
_HEARTBEAT_MAX_MISSES: int = 3
_WS_LLM_RATE_LIMIT = __import__(
    "shared.core.constants", fromlist=["DEFAULT_LLM_RATE_LIMIT_PER_MINUTE"]
).DEFAULT_LLM_RATE_LIMIT_PER_MINUTE


class InterviewWSHandler(
    ConnectionLifecycleMixin,
    TurnCoordinatorMixin,
    VoicePipelineMixin,
    HintServiceMixin,
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
        self.ctx = ConnectionContext(
            ws=websocket,
            session_id=session_id,
            client_access_token=(access_token or "").strip(),
            ws_subprotocol=ws_subprotocol,
            tts_voice=settings.tts_voice,
            session_prosody=VoiceProsody(voice=settings.tts_voice),
            whisper_model=settings.whisper_model,
            nudge_cooldown_sec=float(max(5, int(getattr(settings, "silence_nudge_seconds", 25) or 25))),
            tts_queue=_SentenceTTSQueue(),
        )

    # ── SessionConnection 协议委托属性 ──────────────
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

    def _spawn(self, coro) -> asyncio.Task[Any]:
        """创建后台任务并登记，完成后自动从集合移除。"""
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
        """取消并等待所有后台任务（含报告）。"""
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

    # 兼容旧接口
    _clean_reply = staticmethod(strip_markers)


__all__ = [
    "InterviewWSHandler",
    "_SentenceTTSQueue",
    "_AUDIO_BUFFER_MAX_BYTES",
    "_IMAGE_BASE64_MAX_LEN",
    "_active_handlers",
    "claim_session_connection",
    "release_session_connection",
    "reset_session_registry_for_tests",
    "transcribe_utterance",
    "_pick_stt_text",
    "_should_skip_whisper",
    "_is_echo_of_assistant",
    "_latin_letter_ratio",
    "_normalize_echo_text",
]
