"""面试 WebSocket 单会话单连接租约注册表。

从 ``ws_handler`` 拆出；``WsConnectionRegistry`` 封装进程内状态，对外仅暴露
显式方法，避免模块级可变 dict 成为隐式全局依赖。

部署约束（见 ``docs/deployment-constraints.md``）：
- ``memory``：单 worker / 单实例下保证同 session 仅一条活跃 WS。
- ``database``：``ws_session_leases`` 表记录租约 token；心跳校验 DB 租约。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Protocol

from shared.config import get_settings
from shared.database import sessions_db_session

logger = logging.getLogger(__name__)


class SessionConnection(Protocol):
    """租约持有者最小接口（由 InterviewWSHandler 实现）。"""

    session_id: int
    _superseded: bool

    async def send(self, msg_type: str, **payload) -> None: ...

    @property
    def ws(self): ...


def _lease_token(handler: SessionConnection) -> str:
    token = getattr(handler, "lease_token", None)
    if token:
        return str(token)
    return str(id(handler))


def _persist_lease_sync(session_id: int, lease_token: str) -> None:
    from interview_service.models import WsSessionLease

    with sessions_db_session() as db:
        try:
            row = db.query(WsSessionLease).filter(WsSessionLease.session_id == session_id).first()
            now = datetime.now(timezone.utc)
            if row is None:
                db.add(WsSessionLease(session_id=session_id, lease_token=lease_token, updated_at=now))
            else:
                row.lease_token = lease_token
                row.updated_at = now
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("WS 租约 DB 写入失败 session=%s", session_id, exc_info=True)


def _release_lease_sync(session_id: int, lease_token: str) -> None:
    from interview_service.models import WsSessionLease

    with sessions_db_session() as db:
        try:
            row = (
                db.query(WsSessionLease)
                .filter(WsSessionLease.session_id == session_id)
                .filter(WsSessionLease.lease_token == lease_token)
                .first()
            )
            if row is not None:
                db.delete(row)
                db.commit()
        except Exception:
            db.rollback()
            logger.debug("WS 租约 DB 释放失败 session=%s", session_id, exc_info=True)


def _db_lease_matches_sync(session_id: int, lease_token: str) -> bool:
    from interview_service.models import WsSessionLease

    with sessions_db_session() as db:
        try:
            row = db.query(WsSessionLease).filter(WsSessionLease.session_id == session_id).first()
            if row is None:
                return False
            return row.lease_token == lease_token
        except Exception:
            logger.debug("WS 租约校验失败 session=%s", session_id, exc_info=True)
            return False


class WsConnectionRegistry:
    """进程内 WS 连接租约表（本地单体默认；database 模式配合 DB 心跳校验）。"""

    def __init__(self) -> None:
        self._handlers: dict[int, SessionConnection] = {}
        self._lock = asyncio.Lock()

    async def _supersede_old(self, old: SessionConnection, session_id: int) -> None:
        old._superseded = True
        logger.info(
            "WS 会话租约被顶替 session=%s old=%s new=%s",
            session_id,
            id(old),
            id(self._handlers.get(session_id)),
        )
        try:
            await old.send(
                "error",
                message="该面试已在其他窗口打开，当前连接已被顶替",
                code="B2003",
            )
        except Exception:
            logger.debug("WS 顶替连接通知旧端失败 session=%s", session_id, exc_info=True)
        try:
            await old.ws.close(code=4000)
        except Exception:
            logger.debug("WS 顶替连接关闭旧端失败 session=%s", session_id, exc_info=True)

    async def verify_lease(self, handler: SessionConnection) -> bool:
        """database 模式下校验租约 token；失效则标记 superseded。"""
        cfg = get_settings()
        if cfg.ws_lease_backend != "database":
            return True
        token = _lease_token(handler)
        ok = await asyncio.to_thread(_db_lease_matches_sync, handler.session_id, token)
        if not ok:
            handler._superseded = True
        return ok

    async def claim(self, handler: SessionConnection) -> None:
        """为 handler 占用 session 租约；若已有旧连接则通知并关闭旧连接。"""
        cfg = get_settings()
        token = _lease_token(handler)
        old: SessionConnection | None = None
        async with self._lock:
            old = self._handlers.get(handler.session_id)
            self._handlers[handler.session_id] = handler
            handler._superseded = False
        if cfg.ws_lease_backend == "database":
            await asyncio.to_thread(_persist_lease_sync, handler.session_id, token)
        if old is not None and old is not handler:
            await self._supersede_old(old, handler.session_id)

    async def release(self, handler: SessionConnection) -> None:
        """仅当 handler 仍持有租约时释放（被顶替的旧连接不得误删新连接）。"""
        cfg = get_settings()
        token = _lease_token(handler)
        async with self._lock:
            if self._handlers.get(handler.session_id) is handler:
                self._handlers.pop(handler.session_id, None)
        if cfg.ws_lease_backend == "database":
            await asyncio.to_thread(_release_lease_sync, handler.session_id, token)

    def clear_for_tests(self) -> None:
        self._handlers.clear()

    def snapshot_for_tests(self) -> dict[int, SessionConnection]:
        return self._handlers


_registry: WsConnectionRegistry | None = None


def get_ws_connection_registry() -> WsConnectionRegistry:
    """惰性单例：测试可通过 ``reset_ws_connection_registry`` 替换实例。"""
    global _registry
    if _registry is None:
        _registry = WsConnectionRegistry()
    return _registry


def reset_ws_connection_registry(registry: WsConnectionRegistry | None = None) -> None:
    """测试用：清空或注入自定义注册表。"""
    global _registry
    if registry is None:
        get_ws_connection_registry().clear_for_tests()
        _registry = WsConnectionRegistry()
    else:
        _registry = registry


# ── 模块级薄包装（保持现有 import 路径）────────────────────────
async def verify_connection_lease(handler: SessionConnection) -> bool:
    return await get_ws_connection_registry().verify_lease(handler)


async def claim_session_connection(handler: SessionConnection) -> None:
    await get_ws_connection_registry().claim(handler)


async def release_session_connection(handler: SessionConnection) -> None:
    await get_ws_connection_registry().release(handler)


def reset_session_registry_for_tests() -> None:
    reset_ws_connection_registry()


def active_handlers_for_tests() -> dict[int, SessionConnection]:
    return get_ws_connection_registry().snapshot_for_tests()
