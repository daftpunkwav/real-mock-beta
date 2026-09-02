"""基础 API 服务启动钩子。"""

from __future__ import annotations

import logging

from bootstrap.db_bootstrap import bootstrap_databases_and_seed

logger = logging.getLogger(__name__)


def startup() -> None:
    bootstrap_databases_and_seed()
    logger.info("api-service 启动钩子完成")
