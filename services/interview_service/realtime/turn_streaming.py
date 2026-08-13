"""回合流式消费与 TTS 入队（WS mixin）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.services.interview.agent import ThinkStreamFilter, strip_markers
from interview_service.services.interview.events import EventKind, StreamEvent
from shared.capabilities.voice.tts.edge import (
    extract_emotion,
    next_soft_min,
    should_flush_sentence_buffer,
)

logger = logging.getLogger(__name__)

_IMAGE_BASE64_MAX_LEN: int = 300_000


class TurnStreamingMixin:
    """依赖宿主提供 runner/orchestrator/tts/_spawn/send/_stream_epoch 等。"""

    if TYPE_CHECKING:
        # 宿主字段契约（mypy 可见，运行时跳过）：由 InterviewWSHandler.__init__ 注入
        session_id: int
        runner: Any
        orchestrator: Any
        _stream_epoch: int
        _tts_soft_idx: int
        _awaiting_playback_gen: int
        _tts_queue: Any

        async def send(self, msg_type: str, **payload: Any) -> None: ...
        def _spawn(self, coro) -> Any: ...
        def _begin_playback_wait(self) -> None: ...
        async def _on_request_hint(self, data: dict[str, Any]) -> None: ...

    async def _consume_runner_opening(self, db: Session):
        assert self.runner is not None
        async for event in self.runner.stream_opening(db):
            yield event

    async def _consume_runner_turn(
        self,
        text: str,
        data: dict[str, Any],
        db: Session,
    ):
        assert self.runner is not None
        face = data.get("face_analysis") or self.orchestrator.snapshot.face_analysis
        image_b64 = data.get("image_base64")
        # 与 HTTP 一致：超大 base64 会撑爆内存/LLM 账单，丢弃图像并记日志
        if isinstance(image_b64, str) and len(image_b64) > _IMAGE_BASE64_MAX_LEN:
            logger.warning(
                "WS image_base64 超限 sid=%s len=%d，已丢弃",
                self.session_id,
                len(image_b64),
            )
            image_b64 = None
        self.orchestrator.snapshot.last_user_text = text
        self.orchestrator.snapshot.merge_face(face)

        async for event in self.runner.stream_turn(
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
        """按句入队 TTS，并剥离 think；返回最后一个 TURN_COMPLETE/ERROR。"""
        self._begin_playback_wait()
        sentence_buf = ""
        think_filter = ThinkStreamFilter()
        last: StreamEvent | None = None
        turn_emotion = "neutral"
        epoch = self._stream_epoch
        soft_min, self._tts_soft_idx = next_soft_min(self._tts_soft_idx)
        async for event in events:
            if epoch != self._stream_epoch:
                # 候选人打断：停止消费本轮 LLM/TTS
                return None
            if event.kind == EventKind.TOKEN:
                visible = think_filter.feed(event.token or "")
                if visible:
                    await self.send("assistant_token", token=visible)
                    sentence_buf += visible
                    # 同步捕获句内情绪标记供后续句子使用
                    if "[emotion:" in visible:
                        turn_emotion = extract_emotion(sentence_buf) or turn_emotion
                    if should_flush_sentence_buffer(sentence_buf, soft_min=soft_min):
                        if epoch != self._stream_epoch:
                            return None
                        await self._tts_queue.enqueue(
                            sentence_buf, emotion=turn_emotion
                        )
                        sentence_buf = ""
                        soft_min, self._tts_soft_idx = next_soft_min(self._tts_soft_idx)
            elif event.kind == EventKind.TURN_COMPLETE:
                if epoch != self._stream_epoch:
                    return None
                tail = think_filter.flush()
                if tail:
                    sentence_buf += tail
                    await self.send("assistant_token", token=tail)
                if event.emotion:
                    turn_emotion = event.emotion
                clean = strip_markers(event.content or "")
                await self.send(
                    "assistant_done",
                    content=clean,
                    phase=event.phase_id,
                    is_complete=event.is_complete,
                    emotion=event.emotion,
                    playback_generation=self._awaiting_playback_gen,
                )
                if event.phase_id:
                    await self.send("phase_changed", phase=event.phase_id)
                # 服务端自触发提纲，不依赖客户端往返（避免队头阻塞丢 hint）
                if (
                    auto_hint
                    and not event.is_complete
                    and clean.strip()
                ):
                    self._spawn(self._on_request_hint({"question": clean}))
                if epoch != self._stream_epoch:
                    return None
                if sentence_buf.strip():
                    await self._tts_queue.enqueue(
                        sentence_buf, emotion=turn_emotion
                    )
                    sentence_buf = ""
                if epoch != self._stream_epoch:
                    return None
                await self._tts_queue.flush_remainder("", emotion=turn_emotion)
                if epoch != self._stream_epoch:
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
        if epoch != self._stream_epoch:
            return None
        return last
