"""将 legacy 单文件 ``app.db`` 拆分为 ``api.db`` + ``sessions.db``。"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from shared.config import SHARED_ROOT

logger = logging.getLogger(__name__)

API_TABLES = frozenset(
    {
        "user_profiles",
        "resumes",
        "llm_providers",
        "model_profiles",
        "task_bindings",
        "llm_settings",
        "stage_configs",
        "alembic_version",
    }
)

SESSIONS_TABLES = frozenset(
    {
        "interview_sessions",
        "growth_records",
        "prep_sessions",
        "ws_session_leases",
        "rate_limit_buckets",
        "alembic_version",
    }
)


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> None:
    existing = {
        r[0]
        for r in dst.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if table in existing:
        return
    row = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        return
    dst.execute(row[0])
    cols = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
    col_list = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    rows = src.execute(f"SELECT {col_list} FROM {table}").fetchall()
    if rows:
        dst.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", rows)
    dst.commit()


def split_app_db(
    src_path: Path,
    api_path: Path,
    sessions_path: Path,
) -> bool:
    """从 ``app.db`` 复制表到两个新库；成功返回 True。"""
    if not src_path.is_file():
        return False
    api_path.parent.mkdir(parents=True, exist_ok=True)
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(src_path))
    api_conn = sqlite3.connect(str(api_path))
    sessions_conn = sqlite3.connect(str(sessions_path))
    try:
        src_tables = {
            r[0]
            for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in sorted(src_tables):
            if table.startswith("sqlite_"):
                continue
            if table in API_TABLES:
                _copy_table(src, api_conn, table)
            elif table in SESSIONS_TABLES:
                _copy_table(src, sessions_conn, table)
            else:
                logger.warning("legacy 拆库跳过未知表: %s", table)
        logger.info(
            "已从 %s 拆库到 %s 与 %s",
            src_path.name,
            api_path.name,
            sessions_path.name,
        )
        return True
    finally:
        src.close()
        api_conn.close()
        sessions_conn.close()


def maybe_migrate_legacy_app_db() -> None:
    """若存在 ``app.db`` 且新库不存在，则自动拆分。"""
    data_dir = SHARED_ROOT / "data"
    legacy = data_dir / "app.db"
    api_path = data_dir / "api.db"
    sessions_path = data_dir / "sessions.db"
    if api_path.exists() and sessions_path.exists():
        return
    if not legacy.is_file():
        return
    try:
        split_app_db(legacy, api_path, sessions_path)
    except Exception:
        logger.exception("legacy app.db 拆库失败，将按空库初始化")
