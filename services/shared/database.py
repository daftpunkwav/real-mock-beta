"""数据库连接与会话管理（双库：api.db + sessions.db）。

- **ApiBase** / ``api_engine``：档案、简历、处理器配置（``api_service`` 写权）。
- **SessionsBase** / ``sessions_engine``：面试 / Prep / 租约 / 限流桶。

``Base`` 保留为 ``SessionsBase`` 别名，供会话域 ORM 兼容。
``get_db`` 保留为 ``get_api_db`` 别名（api 路由历史习惯）。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from shared.config import get_settings

logger = logging.getLogger(__name__)


class ApiBase(DeclarativeBase):
    """api.db 元数据（档案 / 简历 / 配置）。"""


class SessionsBase(DeclarativeBase):
    """sessions.db 元数据（会话 / 运行时）。"""


# 会话域模型历史别名
Base = SessionsBase


_api_engine: Engine | None = None
_sessions_engine: Engine | None = None
_ApiSessionLocal: sessionmaker[Session] | None = None
_SessionsSessionLocal: sessionmaker[Session] | None = None
# RLock：``get_*_session_factory`` 在持锁期间会调用 ``get_*_engine``，须可重入。
_engine_lock = threading.RLock()


def _sqlite_engine_kwargs(url: str) -> tuple[dict, dict]:
    connect_args: dict = {}
    pool_kwargs: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if url.endswith(":memory:") or url == "sqlite://":
            from sqlalchemy.pool import StaticPool

            pool_kwargs["poolclass"] = StaticPool
    return connect_args, pool_kwargs


def _attach_sqlite_pragmas(engine: Engine, url: str) -> None:
    if (
        url.startswith("sqlite")
        and ":memory:" not in url
        and url != "sqlite://"
        and "mode=memory" not in url
    ):
        event.listen(engine, "connect", _sqlite_pragmas)


def _sqlite_pragmas(dbapi_conn, _conn_record) -> None:
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
    finally:
        cur.close()


def _ensure_parent_dir(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    db_path = url.replace("sqlite:///", "", 1)
    if db_path.startswith(":") or "mode=memory" in db_path:
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def get_api_engine() -> Engine:
    global _api_engine
    if _api_engine is not None:
        return _api_engine
    with _engine_lock:
        if _api_engine is not None:
            return _api_engine
        settings = get_settings()
        url = settings.api_database_url
        connect_args, pool_kwargs = _sqlite_engine_kwargs(url)
        _api_engine = create_engine(url, connect_args=connect_args, **pool_kwargs)
        _attach_sqlite_pragmas(_api_engine, url)
        _ensure_parent_dir(url)
    return _api_engine


def get_sessions_engine() -> Engine:
    global _sessions_engine
    if _sessions_engine is not None:
        return _sessions_engine
    with _engine_lock:
        if _sessions_engine is not None:
            return _sessions_engine
        settings = get_settings()
        url = settings.sessions_database_url
        connect_args, pool_kwargs = _sqlite_engine_kwargs(url)
        _sessions_engine = create_engine(url, connect_args=connect_args, **pool_kwargs)
        _attach_sqlite_pragmas(_sessions_engine, url)
        _ensure_parent_dir(url)
    return _sessions_engine


def get_engine() -> Engine:
    """向后兼容：返回 sessions 引擎（旧单库语义）。"""
    return get_sessions_engine()


def get_api_session_factory() -> sessionmaker[Session]:
    global _ApiSessionLocal
    if _ApiSessionLocal is not None:
        return _ApiSessionLocal
    with _engine_lock:
        if _ApiSessionLocal is not None:
            return _ApiSessionLocal
        _ApiSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_api_engine()
        )
    return _ApiSessionLocal


def get_sessions_session_factory() -> sessionmaker[Session]:
    global _SessionsSessionLocal
    if _SessionsSessionLocal is not None:
        return _SessionsSessionLocal
    with _engine_lock:
        if _SessionsSessionLocal is not None:
            return _SessionsSessionLocal
        _SessionsSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_sessions_engine()
        )
    return _SessionsSessionLocal


def reset_engines() -> None:
    """测试用：释放双引擎缓存。"""
    global _api_engine, _sessions_engine, _ApiSessionLocal, _SessionsSessionLocal
    with _engine_lock:
        if _api_engine is not None:
            _api_engine.dispose()
        if _sessions_engine is not None:
            _sessions_engine.dispose()
        _api_engine = None
        _sessions_engine = None
        _ApiSessionLocal = None
        _SessionsSessionLocal = None


def __getattr__(name: str):
    """惰性导出，避免 import 时触发引擎创建（须在 setenv 之后）。"""
    if name == "engine":
        return get_sessions_engine()
    if name in ("SessionLocal", "SessionsSessionLocal"):
        return get_sessions_session_factory()
    if name == "ApiSessionLocal":
        return get_api_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_api_db() -> Generator[Session, None, None]:
    db = get_api_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_sessions_db() -> Generator[Session, None, None]:
    db = get_sessions_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """历史别名：api 域路由默认使用 api 库。"""
    yield from get_api_db()


@contextmanager
def api_db_session() -> Generator[Session, None, None]:
    """短生命周期 api 库 Session（工具 / 提示词读档案）。"""
    db = get_api_session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def sessions_db_session() -> Generator[Session, None, None]:
    db = get_sessions_session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_api_db() -> None:
    from shared import models as _api_models  # noqa: F401

    get_api_engine()
    ApiBase.metadata.create_all(bind=get_api_engine())


def init_sessions_db() -> None:
    """创建 sessions 库表。调用前须 ``register_sessions_domain_models()`` 注册 ORM。"""
    get_sessions_engine()
    SessionsBase.metadata.create_all(bind=get_sessions_engine())


def init_db() -> None:
    """创建双库全部表。"""
    init_api_db()
    init_sessions_db()


def dispose_all_engines() -> None:
    """关闭阶段释放双引擎。"""
    reset_engines()


# 兼容旧名
reset_engine = reset_engines
