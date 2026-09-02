"""基础 API 服务启动钩子。"""

from __future__ import annotations

import logging

from shared.core.migrate import run_migrations_all
from shared.database import ApiSessionLocal, init_db
from shared.services.db_bootstrap import bootstrap_databases_and_seed
from shared.services.seed import seed_llm_settings

logger = logging.getLogger(__name__)


def startup() -> None:
    bootstrap_databases_and_seed()
    logger.info("api-service 启动钩子完成")
