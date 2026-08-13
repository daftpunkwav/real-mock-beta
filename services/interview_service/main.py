"""模拟面试服务独立入口（模块化单体阶段用于验证；生产走 services.main 聚合）。

独立运行：``uvicorn interview_service.main:app --port 8083``
"""

from __future__ import annotations

import asyncio
import logging

from interview_service.router import service_router
from interview_service.startup import ensure_rag_index, startup
from shared.app_factory import create_service_app
from shared.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    await asyncio.to_thread(startup)  # 建表 + 迁移
    await ensure_rag_index()


app = create_service_app(
    service_router=service_router,
    title="Interview Service",
    description="RealMock 模拟面试域（面试引擎 / 实时对话 / 报告 / 成长）",
    service_name="interview-service",
    lifespan_startup=_bootstrap,
)
