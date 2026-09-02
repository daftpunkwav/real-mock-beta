"""聚合入口数据库引导（双库 + legacy 拆库）。

归属组合根（``bootstrap`` 包）：建表前须注册业务 ORM，本编排函数依赖
``bootstrap.sessions_orm`` 与各业务包，故不得放在 ``shared`` 平台层
（守卫见 ``tests/test_shared_no_service_imports.py``）。
"""

from __future__ import annotations

import logging
import os

from bootstrap.sessions_orm import register_sessions_domain_models
from shared.core.migrate import run_migrations_all
from shared.database import ApiSessionLocal, dispose_all_engines, init_db
from shared.services.db_split import maybe_migrate_legacy_app_db
from shared.services.seed import seed_llm_settings
from shared.services.pipeline_config import ensure_pipeline_migrated

logger = logging.getLogger(__name__)


def bootstrap_databases_and_seed() -> None:
    """建表、迁移、seed（api 库）。"""
    if os.environ.get("TEST_MODE") == "1":
        # 测试使用 conftest 临时库，跳过 legacy 单文件拆库
        pass
    else:
        maybe_migrate_legacy_app_db()
    register_sessions_domain_models()
    init_db()
    run_migrations_all()
    if os.environ.get("TEST_MODE") == "1":
        logger.debug("TEST_MODE：跳过 seed_llm_settings")
        return
    db = ApiSessionLocal()
    try:
        seed_llm_settings(db)
        ensure_pipeline_migrated(db)
    finally:
        db.close()


def shutdown_databases() -> None:
    """关闭阶段释放双引擎。"""
    dispose_all_engines()
