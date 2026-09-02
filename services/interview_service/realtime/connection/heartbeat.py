"""WS 心跳循环（mixin）：空闲超时探测、server_ping、超时断开。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from interview_service.realtime.core.session_registry import verify_connection_lease

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

_HEARTBEAT_TIMEOUT_SEC: float = 30.0
_HEARTBEAT_MAX_MISSES: int = 3


class HeartbeatMixin:
    """空闲心跳：连续超时未收到消息则提示并断开。"""

    ctx: "ConnectionContext"

    async def next_message(self) -> dict[str, Any] | None:
        """返回下一条待分发消息；连接应结束（超时断开 / 被顶替 / 异常）时返回 None。

        超时未达上限时发送 server_ping 并继续等待；连续 ``_HEARTBEAT_MAX_MISSES`` 次
        超时则发送错误事件并结束循环。
        """
        miss_count = 0
        while not self.ctx.superseded:
            if not await verify_connection_lease(self):
                try:
                    await self.send(
                        "error",
                        message="该面试已在其他窗口打开，当前连接已失效",
                        code="B2003",
                    )
                except Exception:
                    logger.debug(
                        "租约失效通知发送失败 session=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                return None
            try:
                data = await asyncio.wait_for(
                    self.ctx.ws.receive_json(),
                    timeout=_HEARTBEAT_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                if self.ctx.superseded:
                    return None
                miss_count += 1
                if miss_count >= _HEARTBEAT_MAX_MISSES:
                    logger.warning(
                        "WS 心跳超时断开 session=%s miss=%s",
                        self.ctx.session_id, miss_count,
                    )
                    await self.send(
                        "error",
                        message="心跳超时，连接已断开",
                        code="B2002",
                        retryable=True,
                    )
                    return None
                try:
                    await self.send("server_ping", t=int(asyncio.get_event_loop().time() * 1000))
                except Exception:
                    logger.debug(
                        "心跳 server_ping 发送失败 session=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                    return None
                continue
            except Exception:
                logger.debug(
                    "WS 收包异常 session=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
                return None
            if self.ctx.superseded:
                return None
            return data
        return None


__all__ = ["HeartbeatMixin", "_HEARTBEAT_TIMEOUT_SEC", "_HEARTBEAT_MAX_MISSES"]
