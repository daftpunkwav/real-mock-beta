"""基础 API 服务启动钩子。

- ``startup``：建表/迁移（过渡期经 shared.init_db 聚合注册）+ 从环境变量
  seed 处理器配置（seed 唯一实现位于 ``shared.services.seed``）。
"""

from __future__ import annotations

import logging

from shared.database import init_db, SessionLocal
from shared.core.migrate import run_migrations
from shared.database import engine
from shared.services.seed import seed_llm_settings

logger = logging.getLogger(__name__)


def startup() -> None:
    """同步初始化：建表 + 迁移 + 处理器配置 seed。"""
    init_db()
    run_migrations(engine)
    db = SessionLocal()
    try:
        seed_llm_settings(db)
    finally:
        db.close()
    logger.info("api-service 启动钩子完成")
