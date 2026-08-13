"""``app.core.migrate`` 单元测试。

覆盖：

- 初次运行：对已有表补齐缺失列；
- 二次运行：已存在列应跳过（idempotent），不应报 DuplicateColumn；
- 异常路径：若 SQL 执行失败，该表迁移失败被吞掉，其他表正常完成；
- 表不存在的迁移项应被静默跳过，不影响其他表。
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from shared.core.migrate import _column_name_from_stmt, run_migrations
from shared.database import Base


def _fresh_engine():
    """返回全新 :memory: 引擎，仅建表不执行迁移，便于断言前/后状态。"""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    return eng


def test_column_name_extraction() -> None:
    """``_column_name_from_stmt`` 抽取裸列名（兼容引号包裹）。"""
    assert _column_name_from_stmt(
        "ALTER TABLE x ADD COLUMN foo VARCHAR(20) DEFAULT ''"
    ) == "foo"
    assert _column_name_from_stmt(
        "ALTER TABLE x ADD COLUMN `bar` VARCHAR(20) DEFAULT 0"
    ) == "bar"
    assert _column_name_from_stmt("ALTER TABLE x DROP COLUMN z") is None
    assert _column_name_from_stmt("") is None


def test_run_migrations_is_idempotent() -> None:
    """运行两次迁移：第二次应为空（验证幂等），不报 DuplicateColumn。

    使用合成表 + 临时注入 MIGRATIONS，避免依赖「模型缺列、迁移补齐」的漂移假设
    （当模型已包含全部列时 create_all 后 applied 会为空）。
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _mig_test (id INTEGER PRIMARY KEY)"))

    from shared.core import migrate

    original = dict(migrate.MIGRATIONS)
    migrate.MIGRATIONS = {
        "_mig_test": [
            "ALTER TABLE _mig_test ADD COLUMN foo VARCHAR(20) DEFAULT ''",
            "ALTER TABLE _mig_test ADD COLUMN bar INTEGER DEFAULT 0",
        ]
    }
    try:
        first = run_migrations(eng)
        second = run_migrations(eng)
        assert "_mig_test" in first
        assert len(first["_mig_test"]) == 2
        assert "_mig_test" not in second
        cols = {c["name"] for c in inspect(eng).get_columns("_mig_test")}
        assert "foo" in cols and "bar" in cols
    finally:
        migrate.MIGRATIONS = original


def test_run_migrations_skips_missing_table() -> None:
    """如果迁移清单里的表不存在，不应 crash；其它表仍可完成。"""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _mig_ok (id INTEGER PRIMARY KEY)"))

    from shared.core import migrate

    original = dict(migrate.MIGRATIONS)
    migrate.MIGRATIONS = {
        "_mig_missing": [
            "ALTER TABLE _mig_missing ADD COLUMN x VARCHAR(10) DEFAULT ''",
        ],
        "_mig_ok": [
            "ALTER TABLE _mig_ok ADD COLUMN y VARCHAR(10) DEFAULT ''",
        ],
    }
    try:
        applied = run_migrations(eng)
        assert "_mig_missing" not in applied
        assert "_mig_ok" in applied
    finally:
        migrate.MIGRATIONS = original


def test_failed_alter_silently_continues_other_tables() -> None:
    """对单张表注入不合法 SQL：该表失败被吞掉；其他表正常完成。"""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE _mig_bad (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE _mig_good (id INTEGER PRIMARY KEY)"))

    from shared.core import migrate

    original = dict(migrate.MIGRATIONS)
    migrate.MIGRATIONS = {
        "_mig_bad": [
            # 故意语法错误，触发 OperationalError
            "ALTER TABLE _mig_bad ADD COLUMN !!!",
        ],
        "_mig_good": [
            "ALTER TABLE _mig_good ADD COLUMN ok VARCHAR(10) DEFAULT ''",
        ],
    }
    try:
        applied = run_migrations(eng)
    finally:
        migrate.MIGRATIONS = original

    assert "_mig_bad" not in applied
    assert "_mig_good" in applied
    cols = {c["name"] for c in inspect(eng).get_columns("_mig_good")}
    assert "ok" in cols


def test_run_migrations_stamps_alembic_version() -> None:
    """run_migrations 应写入 alembic_version=head。"""
    from shared.core.migrate import ALEMBIC_HEAD_REVISION

    eng = _fresh_engine()
    run_migrations(eng)
    with eng.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    assert row is not None
    assert row[0] == ALEMBIC_HEAD_REVISION

