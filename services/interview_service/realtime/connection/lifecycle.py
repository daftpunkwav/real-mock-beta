"""WS 连接生命周期（mixin）：消息收发基元、主循环、清理。

职责已按依赖方向拆出：
- :mod:`connection_auth` — 鉴权 / 会话绑定 / 管道装配 / 开场推进；
- :mod:`heartbeat` — 空闲心跳与超时断开；
- :mod:`message_dispatcher` — 入站消息分发与音频缓冲。

本模块保留主循环 :meth:`handle`、收发基元与失败关闭路径。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import WebSocketDisconnect

from shared.core.logging import set_trace_id
from shared.database import SessionLocal
from interview_service.realtime.core.events import TurnState
from interview_service.realtime.core.session_registry import release_session_connection

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ConnectionLifecycleMixin:
    """WS 主循环：握手、鉴权装配、消息循环、清理。"""

    ctx: "ConnectionContext"

    async def send(self, msg_type: str, **payload: Any) -> None:
        await self.ctx.ws.send_json({"type": msg_type, **payload})

    async def _tts_send(self, msg_type: str, **payload: Any) -> None:
        """TTS 通道发送：附带 playback_generation 供客户端回传。"""
        if msg_type == "tts_audio":
            payload.setdefault("playback_generation", self.ctx.awaiting_playback_gen)
        await self.send(msg_type, **payload)

    async def set_turn(self, state: TurnState) -> None:
        self.ctx.turn_state = state
        if state == TurnState.USER_SPEAKING:
            self.ctx.mic_opened_at = asyncio.get_event_loop().time()
        await self.send("turn_state", state=state.value)

    async def _fail_and_close(
        self,
        message: str,
        code: int = 4401,
        *,
        error_code: str = "B2001",
        retryable: bool = False,
    ) -> None:
        try:
            await self.send(
                "error",
                message=message,
                code=error_code,
                retryable=retryable,
            )
        except Exception:
            logger.debug(
                "fail_and_close 发送 error 失败 sid=%s",
                self.ctx.session_id,
                exc_info=True,
            )
        try:
            await self.ctx.ws.close(code=code)
        except Exception:
            logger.debug(
                "fail_and_close 关闭 WS 失败 sid=%s",
                self.ctx.session_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def handle(self) -> None:
        accept_kwargs: dict[str, str] = {}
        if self.ctx.ws_subprotocol:
            accept_kwargs["subprotocol"] = self.ctx.ws_subprotocol
        await self.ctx.ws.accept(**accept_kwargs)
        ws_tid = f"ws-{self.ctx.session_id}-{uuid.uuid4().hex[:8]}"
        set_trace_id(ws_tid)
        db = SessionLocal()
        try:
            session = await self.authenticate(db)
            if session is None:
                return
            if not await self.bind_pipeline(db, session):
                return
            await self.start_session_flow(session, db)
            while True:
                data = await self.next_message()
                if data is None:
                    break
                await self._dispatch(data, db, session)
        except WebSocketDisconnect:
            logger.info("WS 断开 session=%s", self.ctx.session_id)
        except Exception as e:
            logger.exception("WS 错误: %s", e)
            try:
                await self.set_turn(TurnState.USER_SPEAKING)
                await self.send(
                    "error",
                    message="服务端异常，已恢复 USER_SPEAKING",
                    code="B2001",
                    retryable=True,
                )
            except Exception:
                logger.debug(
                    "WS 异常恢复通知发送失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "WS 异常路径 rollback 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            await self._teardown(db)

    async def _teardown(self, db: Any) -> None:
        """释放租约、取消后台任务、关闭 TTS 队列与 DB 会话。"""
        try:
            await release_session_connection(self)
        except Exception:
            logger.exception("释放会话租约失败")
        try:
            await self._cancel_bg_tasks()
        except Exception:
            logger.exception("取消后台任务失败")
        try:
            await asyncio.wait_for(self.ctx.tts_queue.stop(), timeout=5.0)
        except Exception:
            logger.exception("TTS queue 关闭失败")
        try:
            db.close()
        except Exception:
            logger.exception("DB 关闭失败")


__all__ = ["ConnectionLifecycleMixin"]
