"""基础 API 服务独立入口（模块化单体阶段用于验证；生产走 services.main 聚合）。

独立运行：``uvicorn api_service.main:app --port 8081``
"""

from __future__ import annotations

import asyncio
import logging

from api_service.router import service_router
from api_service.startup import startup
from shared.app_factory import create_service_app
from shared.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    await asyncio.to_thread(startup)


app = create_service_app(
    service_router=service_router,
    title="API Service",
    description="RealMock 基础后端 API（档案 / 简历 / 处理器配置）",
    service_name="api-service",
    lifespan_startup=_bootstrap,
)
