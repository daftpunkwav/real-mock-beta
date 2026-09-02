"""基础 API 服务路由聚合。

暴露 ``service_router``（纯路由，无版本前缀），由调用方注入 ``/api/v1``
（聚合入口还会为兼容别名注入 ``/api``）；独立部署见 ``main.create_app``。
"""

from __future__ import annotations

from fastapi import APIRouter

from api_service.routes import profile
from api_service.routes.resume import router as resume_router
from api_service.routes.settings import models_router, router as settings_router

service_router = APIRouter()
service_router.include_router(profile.router, prefix="/profile", tags=["profile"])
service_router.include_router(resume_router, prefix="/resume", tags=["resume"])
service_router.include_router(settings_router, prefix="/settings", tags=["settings"])
service_router.include_router(models_router, prefix="/settings", tags=["settings"])
