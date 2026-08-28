"""智能体服务独立入口（模块化单体阶段用于验证；生产走 services.main 聚合）。

独立运行：``uvicorn agent_service.main:app --port 8082``
"""

from __future__ import annotations

import asyncio
import logging

from agent_service.router import service_router
from agent_service.startup import startup
from shared.app_factory import create_service_app
from shared.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    await asyncio.to_thread(startup)  # 建表 + 迁移 + 处理器配置 seed


app = create_service_app(
    service_routers=service_router,
    title="Agent Service",
    description="RealMock 智能体服务（面试准备教练）",
    service_name="agent-service",
    lifespan_startup=_bootstrap,
)
