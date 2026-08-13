"""SQLite 列补全迁移（实现）+ Alembic 版本戳。

列级幂等迁移仍由本模块的 ``MIGRATIONS`` / ``apply_column_migrations`` 完成；
Alembic 负责 ``alembic_version`` 追踪，便于后续增量 revision。
启动路径：``run_migrations(engine)`` → apply + stamp head。
CLI：``alembic upgrade head``（见 ``alembic/versions``）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError

logger = logging.getLogger(__name__)

# 与 alembic/versions 中 revision id 对齐
ALEMBIC_HEAD_REVISION = "20260803_0001"

# table -> [ALTER 语句列表]
MIGRATIONS: dict[str, list[str]] = {
    "user_profiles": [
        "ALTER TABLE user_profiles ADD COLUMN gender VARCHAR(20) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN identity VARCHAR(50) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN school VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN major VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN graduation_year VARCHAR(20) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN work_years_detail VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN current_company VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN expected_salary VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN self_intro TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN github_username VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN portfolio_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN linkedin_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN city VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN preferred_languages VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN career_highlights TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN open_to_remote VARCHAR(20) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN notice_period VARCHAR(50) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN education_level VARCHAR(50) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN expected_city VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN email VARCHAR(200) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN phone VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN certificates TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN english_level VARCHAR(100) DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN signature_projects TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN strengths TEXT DEFAULT ''",
        "ALTER TABLE user_profiles ADD COLUMN weaknesses TEXT DEFAULT ''",
    ],
    "llm_settings": [
        "ALTER TABLE llm_settings ADD COLUMN protocol VARCHAR(50) DEFAULT 'openai_chat'",
        "ALTER TABLE llm_settings ADD COLUMN reasoning_effort VARCHAR(20) DEFAULT 'medium'",
        "ALTER TABLE llm_settings ADD COLUMN supports_vision BOOLEAN DEFAULT 1",
        "ALTER TABLE llm_settings ADD COLUMN supports_audio BOOLEAN DEFAULT 0",
        "ALTER TABLE llm_settings ADD COLUMN stt_model VARCHAR(50) DEFAULT 'base'",
        "ALTER TABLE llm_settings ADD COLUMN tts_voice VARCHAR(100) DEFAULT 'zh-CN-XiaoxiaoNeural'",
        "ALTER TABLE llm_settings ADD COLUMN speech_recognize_handler VARCHAR(50) DEFAULT 'local'",
        "ALTER TABLE llm_settings ADD COLUMN speech_recognize_mode VARCHAR(30) DEFAULT 'transcribe'",
        "ALTER TABLE llm_settings ADD COLUMN asr_api_base VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_api_key VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_model VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_app_id VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_api_secret VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_access_key VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_resource_id VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN asr_app_key VARCHAR(100) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN speech_speak_handler VARCHAR(50) DEFAULT 'edge'",
        "ALTER TABLE llm_settings ADD COLUMN speech_speak_mode VARCHAR(30) DEFAULT 'tts_from_text'",
        "ALTER TABLE llm_settings ADD COLUMN tts_api_base VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN tts_api_key VARCHAR(500) DEFAULT ''",
        "ALTER TABLE llm_settings ADD COLUMN tts_model VARCHAR(100) DEFAULT ''",
    ],
    "stage_configs": [
        "CREATE TABLE IF NOT EXISTS stage_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, stage VARCHAR(30) NOT NULL UNIQUE, provider VARCHAR(100) DEFAULT '', api_base VARCHAR(500) DEFAULT '', api_key VARCHAR(500) DEFAULT '', protocol VARCHAR(50) DEFAULT 'openai_chat', model VARCHAR(100) DEFAULT '', max_tokens INTEGER DEFAULT 4096, context_window INTEGER DEFAULT 128000, supports_vision BOOLEAN DEFAULT 0, supports_audio_input BOOLEAN DEFAULT 0, supports_audio_output BOOLEAN DEFAULT 0, supports_video_input BOOLEAN DEFAULT 0, fallback_handler VARCHAR(100) DEFAULT '', fallback_mode VARCHAR(30) DEFAULT '', extras TEXT DEFAULT '{}', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    ],
    "resumes": [
        "ALTER TABLE resumes ADD COLUMN is_active BOOLEAN DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN score INTEGER",
        "ALTER TABLE resumes ADD COLUMN analysis TEXT DEFAULT '{}'",
    ],
    "interview_sessions": [
        "ALTER TABLE interview_sessions ADD COLUMN avatar_id VARCHAR(50) DEFAULT 'professional_male'",
        "ALTER TABLE interview_sessions ADD COLUMN scene_id VARCHAR(50) DEFAULT 'meeting_room'",
        "ALTER TABLE interview_sessions ADD COLUMN token_usage INTEGER DEFAULT 0",
        "ALTER TABLE interview_sessions ADD COLUMN access_token VARCHAR(64) DEFAULT ''",
    ],
    "prep_sessions": [
        "ALTER TABLE prep_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'active'",
        "ALTER TABLE prep_sessions ADD COLUMN access_token VARCHAR(64) DEFAULT ''",
    ],
}


def _column_name_from_stmt(stmt: str) -> str | None:
    """从 ALTER ADD COLUMN 语句抽取列名。"""
    try:
        marker = "ADD COLUMN"
        idx = stmt.upper().find(marker)
        if idx < 0:
            return None
        rest = stmt[idx + len(marker) :].strip()
        token = rest.split()[0] if rest else ""
        return token.strip('"').strip("`").strip("[]") or None
    except Exception:
        return None


def apply_column_migrations(engine: Engine) -> dict[str, list[str]]:
    """幂等补齐缺失列。返回 ``{table: [applied_sql, ...]}``。"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: dict[str, list[str]] = {}

    for table, statements in MIGRATIONS.items():
        if table not in existing_tables:
            create_statements = [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith("CREATE TABLE")
            ]
            if not create_statements:
                continue
            try:
                with engine.begin() as conn:
                    for statement in create_statements:
                        conn.execute(text(statement))
                applied[table] = create_statements
                existing_tables.add(table)
            except Exception as e:
                logger.error("迁移失败 %s（建表事务已回滚）: %s", table, e, exc_info=True)
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        to_apply: list[str] = [
            s
            for s in statements
            if (col := _column_name_from_stmt(s)) and col not in existing_cols
        ]
        if not to_apply:
            continue
        try:
            with engine.begin() as conn:
                for stmt in to_apply:
                    conn.execute(text(stmt))
                    logger.info("迁移成功: %s", stmt[:80])
            applied[table] = to_apply
        except (OperationalError, IntegrityError) as e:
            logger.error("迁移失败 %s（事务已回滚）: %s", table, e, exc_info=True)
        except Exception as e:
            logger.error(
                "迁移失败 %s（事务已回滚，未知异常类型）: %s",
                table,
                e,
                exc_info=True,
            )

    if applied:
        logger.info(
            "数据库迁移完成，共 %d 张表 %d 列新增",
            len(applied),
            sum(len(v) for v in applied.values()),
        )
    else:
        logger.debug("数据库无需列迁移")
    return applied


def stamp_alembic_head(engine: Engine, revision: str = ALEMBIC_HEAD_REVISION) -> None:
    """确保 alembic_version 指向当前 head（兼容已有库首次接入 Alembic）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY"
                ")"
            )
        )
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        if row is None:
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": revision},
            )
        elif row[0] != revision:
            conn.execute(
                text("UPDATE alembic_version SET version_num = :v"),
                {"v": revision},
            )


def run_migrations(engine: Engine) -> dict[str, list[str]]:
    """启动入口：列补全 + Alembic 版本戳。"""
    applied = apply_column_migrations(engine)
    try:
        stamp_alembic_head(engine)
    except Exception:
        logger.exception("写入 alembic_version 失败（列迁移已完成）")
    return applied


def alembic_config_path() -> Path:
    """backend/alembic.ini。"""
    return Path(__file__).resolve().parents[2] / "alembic.ini"
