"""WS 入站消息分发（mixin）：audio_chunk / stt_text / user_turn_end / 各类请求。"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from interview_service.agents.vision.agent import VisionAgent
from interview_service.models import InterviewSession
from interview_service.realtime.events import TurnState
from shared.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, MAX_USER_TEXT_CHARS
from shared.core.ratelimit import try_rate_limit_by_id

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)

# 音频缓冲上限：约 5MB（与旧 _AUDIO_BUFFER_MAX_BYTES 一致）
AUDIO_BUFFER_MAX_BYTES: int = 5 * 1024 * 1024
_WS_LLM_RATE_LIMIT = DEFAULT_LLM_RATE_LIMIT_PER_MINUTE


class MessageDispatcherMixin:
    """按消息类型分发；依赖 ctx 字段与 _spawn / send / set_turn。"""

    ctx: "ConnectionContext"

    def _llm_rate_limited(self, *, limit: int) -> bool:
        if not try_rate_limit_by_id(
            key="llm",
            client_id=f"ws-{self.ctx.session_id}",
            limit=limit,
        ):
            return True
        return False

    async def _dispatch(self, data: dict[str, Any], db: Session, session: InterviewSession) -> None:
        msg_type = data.get("type", "")
        if msg_type == "audio_chunk":
            await self._on_audio_chunk(data)
        elif msg_type == "stt_text":
            text = data.get("text", "").strip()
            if text:
                await self.send("stt_partial", text=text)
        elif msg_type == "pong":
            return
        elif msg_type == "vision_update":
            face = data.get("face_analysis")
            if face:
                self.ctx.orchestrator.snapshot.merge_face(face)
                self.ctx.orchestrator.snapshot.vision_summary = VisionAgent.summarize(face)
        elif msg_type == "user_turn_end":
            if not self._can_start_user_turn():
                return
            if self._llm_rate_limited(limit=_WS_LLM_RATE_LIMIT):
                await self._send_rate_limited()
                return
            self._spawn(self._run_user_turn_end(data))
        elif msg_type == "silence_timeout":
            if self.ctx.turn_busy or self.ctx.closing:
                return
            self._spawn(self._on_silence_nudge())
        elif msg_type == "barge_in":
            if self.ctx.closing:
                return
            self._spawn(self._on_candidate_barge_in())
        elif msg_type == "user_text":
            await self._on_user_text(data)
        elif msg_type == "request_hint":
            if self._llm_rate_limited(limit=max(5, _WS_LLM_RATE_LIMIT // 2)):
                await self._send_rate_limited()
                return
            self._spawn(self._on_request_hint(data))
        elif msg_type == "request_finish":
            if self.ctx.closing:
                return
            self._spawn(self._on_request_finish())
        elif msg_type == "tts_playback_done":
            client_gen = data.get("generation")
            if client_gen is None or client_gen == self.ctx.awaiting_playback_gen:
                self.ctx.playback_done.set()
        else:
            logger.warning("未知 WS 消息类型 sid=%s type=%s", self.ctx.session_id, msg_type)

    async def _send_rate_limited(self) -> None:
        await self.send(
            "error",
            message="请求过于频繁，请稍后再试",
            code="A0002",
            retryable=True,
        )

    async def _on_audio_chunk(self, data: dict[str, Any]) -> None:
        chunk = data.get("data", "")
        if not chunk:
            return
        try:
            new_bytes = len(base64.b64decode(chunk, validate=False))
        except Exception:
            new_bytes = 0
        if self.ctx.audio_buffer_bytes + new_bytes > AUDIO_BUFFER_MAX_BYTES:
            logger.warning(
                "audio_buffer 超上限 session=%s bytes=%s",
                self.ctx.session_id,
                self.ctx.audio_buffer_bytes + new_bytes,
            )
            await self.send(
                "error",
                message="音频缓存超限，请先结束当前回合",
                code="A0004",
            )
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0
            return
        self.ctx.audio_buffer.append(chunk)
        self.ctx.audio_buffer_bytes += new_bytes

    async def _on_user_text(self, data: dict[str, Any]) -> None:
        text = data.get("text", "").strip()
        if len(text) > MAX_USER_TEXT_CHARS:
            await self.send(
                "error",
                message=f"文本过长（上限 {MAX_USER_TEXT_CHARS} 字符）",
                code="A0003",
            )
            return
        if (
            text
            and self.ctx.turn_state == TurnState.USER_SPEAKING
            and self._can_start_user_turn()
        ):
            if self._llm_rate_limited(limit=_WS_LLM_RATE_LIMIT):
                await self._send_rate_limited()
                return
            self._spawn(self._run_user_text(text, data))


__all__ = ["MessageDispatcherMixin", "AUDIO_BUFFER_MAX_BYTES"]
