"""回合流式消费与 TTS 入队（WS mixin）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.services.interview.agent_text import strip_markers
from interview_service.services.interview.events import EventKind, StreamEvent
from shared.capabilities.voice.tts.edge import (
    next_soft_min,
    should_flush_sentence_buffer,
)

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)

_IMAGE_BASE64_MAX_LEN: int = 300_000


class TurnStreamingMixin:
    """回合流式消费；依赖 ctx.runner/orchestrator/tts_queue/stream_epoch 等。"""

    ctx: "ConnectionContext"

    async def _consume_runner_opening(self, db: Session):
        assert self.ctx.runner is not None
        async for event in self.ctx.runner.stream_opening(db):
            yield event

    async def _consume_runner_turn(
        self,
        text: str,
        data: dict[str, Any],
        db: Session,
    ):
        assert self.ctx.runner is not None
        face = data.get("face_analysis") or self.ctx.orchestrator.snapshot.face_analysis
        image_b64 = data.get("image_base64")
        if isinstance(image_b64, str) and len(image_b64) > _IMAGE_BASE64_MAX_LEN:
            logger.warning(
                "WS image_base64 超限 sid=%s len=%d，已丢弃",
                self.ctx.session_id,
                len(image_b64),
            )
            image_b64 = None
        self.ctx.orchestrator.snapshot.last_user_text = text
        self.ctx.orchestrator.snapshot.merge_face(face)

        async for event in self.ctx.runner.stream_turn(
            text,
            db,
            face=face,
            image_b64=image_b64,
        ):
            yield event

    async def _stream_events_with_tts(
        self,
        events,
        *,
        db: Session | None = None,
        session: InterviewSession | None = None,
        auto_hint: bool = True,
    ) -> StreamEvent | None:
        """按句入队 TTS；返回最后一个 TURN_COMPLETE/ERROR。

        runner 已按 say-first 协议解析：TOKEN 均为 say 明文（think 已剥离），
        TURN_COMPLETE 携带控制字段（emotion/wait_seconds/sources）。
        """
        self._begin_playback_wait()
        sentence_buf = ""
        last: StreamEvent | None = None
        turn_emotion = "neutral"
        epoch = self.ctx.stream_epoch
        soft_min, self.ctx.tts_soft_idx = next_soft_min(self.ctx.tts_soft_idx)
        async for event in events:
            if epoch != self.ctx.stream_epoch:
                return None
            if event.kind == EventKind.TOKEN:
                visible = event.token or ""
                if visible:
                    await self.send("assistant_token", token=visible)
                    sentence_buf += visible
                    if should_flush_sentence_buffer(sentence_buf, soft_min=soft_min):
                        if epoch != self.ctx.stream_epoch:
                            return None
                        await self.ctx.tts_queue.enqueue(
                            sentence_buf, emotion=turn_emotion
                        )
                        sentence_buf = ""
                        soft_min, self.ctx.tts_soft_idx = next_soft_min(self.ctx.tts_soft_idx)
            elif event.kind == EventKind.TURN_COMPLETE:
                if epoch != self.ctx.stream_epoch:
                    return None
                if event.emotion:
                    turn_emotion = event.emotion
                clean = strip_markers(event.content or "")
                await self.send(
                    "assistant_done",
                    content=clean,
                    phase=event.phase_id,
                    is_complete=event.is_complete,
                    emotion=event.emotion,
                    wait_seconds=event.wait_seconds,
                    sources=list(event.sources),
                    playback_generation=self.ctx.awaiting_playback_gen,
                )
                if event.phase_id:
                    await self.send("phase_changed", phase=event.phase_id)
                if (
                    auto_hint
                    and not event.is_complete
                    and clean.strip()
                ):
                    self._spawn(self._on_request_hint({"question": clean}))
                if epoch != self.ctx.stream_epoch:
                    return None
                if sentence_buf.strip():
                    await self.ctx.tts_queue.enqueue(
                        sentence_buf, emotion=turn_emotion
                    )
                    sentence_buf = ""
                if epoch != self.ctx.stream_epoch:
                    return None
                await self.ctx.tts_queue.flush_remainder("", emotion=turn_emotion)
                if epoch != self.ctx.stream_epoch:
                    return None
                last = event
            elif event.kind == EventKind.ERROR:
                await self.send(
                    "error",
                    message=event.error,
                    code=event.error_code or "C0001",
                    retryable=event.error_retryable,
                )
                last = event
        if epoch != self.ctx.stream_epoch:
            return None
        return last
