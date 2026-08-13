"""智能体服务路由聚合。

暴露 ``service_router``（纯路由）供聚合入口 include；独立部署由
``agent_service.main.create_app`` 组合。
"""

from __future__ import annotations

from fastapi import APIRouter

from agent_service.routes import prep

service_router = APIRouter()
service_router.include_router(prep.router, prefix="/prep", tags=["prep"])
