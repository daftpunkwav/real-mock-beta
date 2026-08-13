"""模拟面试服务路由聚合。

暴露 ``service_router``（纯路由）供聚合入口 include；独立部署由
``interview_service.main.create_app`` 组合。
"""

from __future__ import annotations

from fastapi import APIRouter

from interview_service.routes import interview, options, reports, ws_interview

service_router = APIRouter()
service_router.include_router(interview.router, prefix="/interview", tags=["interview"])
service_router.include_router(reports.router, prefix="/reports", tags=["reports"])
service_router.include_router(options.router, prefix="/options", tags=["options"])
service_router.include_router(ws_interview.router, tags=["realtime"])
