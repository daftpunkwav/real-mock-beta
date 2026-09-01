"""播放等待（WS mixin）：TTS 发送世代对齐、等待客户端播完再开麦。

拆自 :mod:`...turn_coordinator`。世代与房间 hook / TTS 队列共用
``ctx.playback_generation`` / ``ctx.awaiting_playback_gen``，不另造计数器。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from interview_service.realtime.events import TurnState

if TYPE_CHECKING:
    from interview_service.realtime.context import ConnectionContext

logger = logging.getLogger(__name__)


class TurnPlaybackMixin:
    """播放等待：提升世代、等待 ``tts_playback_done``（或超时）、再切开麦。"""

    ctx: "ConnectionContext"

    def _mark_tts_sent(self) -> None:
        self.ctx.tts_sent_this_turn = True

    def _begin_playback_wait(self) -> None:
        """新回合开始：提升世代并清空完成信号。"""
        self.ctx.playback_generation += 1
        self.ctx.awaiting_playback_gen = self.ctx.playback_generation
        self.ctx.tts_sent_this_turn = False
        self.ctx.playback_done.clear()

    async def _wait_client_playback(self) -> None:
        """若本回合发过 TTS，则等待客户端 tts_playback_done（或超时）。"""
        if not self.ctx.tts_sent_this_turn:
            return
        wait_gen = self.ctx.awaiting_playback_gen
        if not self.ctx.playback_done.is_set():
            try:
                await asyncio.wait_for(
                    self.ctx.playback_done.wait(),
                    timeout=self.ctx.playback_wait_timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "tts_playback_done 超时 sid=%s gen=%s，继续",
                    self.ctx.session_id,
                    wait_gen,
                )
        await asyncio.sleep(0.15)
        if self.ctx.awaiting_playback_gen == wait_gen:
            self.ctx.tts_sent_this_turn = False
            self.ctx.playback_done.clear()

    async def _open_mic_after_playback(self) -> None:
        """服务端合成发完后，等客户端播完（或超时）再切 USER_SPEAKING，防回采。"""
        wait_epoch = self.ctx.stream_epoch
        await self._wait_client_playback()
        if wait_epoch != self.ctx.stream_epoch:
            return
        if self.ctx.turn_state == TurnState.USER_SPEAKING:
            return
        await self.set_turn(TurnState.USER_SPEAKING)


__all__ = ["TurnPlaybackMixin"]
