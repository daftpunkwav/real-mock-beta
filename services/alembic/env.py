"""Alembic 环境：使用应用 Settings.database_url（聚合层）。

注册三服务全部模型到 metadata：
- shared.models：StageConfig / LLMSettings / UserProfile / Resume
- agent_service.models、interview_service.models：业务表
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.config import get_settings
from shared.database import ApiBase, SessionsBase

# 确保三服务全部模型注册到 metadata（共享库单库聚合）
import shared.models  # noqa: F401
import agent_service.models  # noqa: F401
import interview_service.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ApiBase.metadata


def get_url() -> str:
    return get_settings().api_database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
