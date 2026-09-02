"""模拟面试服务路由聚合。

暴露 ``service_router``（纯路由）供聚合入口 include；独立部署由
``interview_service.main.create_app`` 组合。
"""

from __future__ import annotations

from fastapi import APIRouter

from interview_service.routes import options
from interview_service.routes.interview import router as interview_router
from interview_service.routes.growth import router as growth_router
from interview_service.routes.reports import router as reports_router
from interview_service.routes.ws import router as ws_router

service_router = APIRouter()
service_router.include_router(interview_router, prefix="/interview", tags=["interview"])
service_router.include_router(reports_router, prefix="/reports", tags=["reports"])
service_router.include_router(growth_router, prefix="/growth", tags=["growth"])
service_router.include_router(options.router, prefix="/options", tags=["options"])
service_router.include_router(ws_router, tags=["realtime"])
