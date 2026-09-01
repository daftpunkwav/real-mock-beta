"""面试 WebSocket 单会话单连接租约注册表。

从 ``ws_handler`` 拆出，避免连接互斥逻辑与回合业务混杂。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SessionConnection(Protocol):
    """租约持有者最小接口（由 InterviewWSHandler 实现）。"""

    session_id: int
    _superseded: bool

    async def send(self, msg_type: str, **payload) -> None: ...

    @property
    def ws(self): ...


_active_handlers: dict[int, SessionConnection] = {}
_registry_lock = asyncio.Lock()


async def claim_session_connection(handler: SessionConnection) -> None:
    """为 handler 占用 session 租约；若已有旧连接则通知并关闭旧连接。"""
    old: SessionConnection | None = None
    async with _registry_lock:
        old = _active_handlers.get(handler.session_id)
        _active_handlers[handler.session_id] = handler
        handler._superseded = False
    if old is not None and old is not handler:
        old._superseded = True
        logger.info(
            "WS 会话租约被顶替 session=%s old=%s new=%s",
            handler.session_id,
            id(old),
            id(handler),
        )
        try:
            await old.send(
                "error",
                message="该面试已在其他窗口打开，当前连接已被顶替",
                code="B2003",
            )
        except Exception:
            logger.debug("WS 顶替连接通知旧端失败 session=%s", handler.session_id, exc_info=True)
        try:
            await old.ws.close(code=4000)
        except Exception:
            logger.debug("WS 顶替连接关闭旧端失败 session=%s", handler.session_id, exc_info=True)


async def release_session_connection(handler: SessionConnection) -> None:
    """仅当 handler 仍持有租约时释放（被顶替的旧连接不得误删新连接）。"""
    async with _registry_lock:
        if _active_handlers.get(handler.session_id) is handler:
            _active_handlers.pop(handler.session_id, None)


def reset_session_registry_for_tests() -> None:
    """测试用：清空会话连接注册表。"""
    _active_handlers.clear()


def active_handlers_for_tests() -> dict[int, SessionConnection]:
    """测试用：暴露注册表视图。"""
    return _active_handlers
