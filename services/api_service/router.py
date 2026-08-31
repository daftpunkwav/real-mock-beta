"""基础 API 服务路由聚合。

暴露 ``service_router``（纯路由，无版本前缀），由调用方注入 ``/api/v1``
（聚合入口还会为兼容别名注入 ``/api``）；独立部署见 ``main.create_app``。
"""

from __future__ import annotations

from fastapi import APIRouter

from api_service.routes import models, profile, resume, settings

service_router = APIRouter()
service_router.include_router(profile.router, prefix="/profile", tags=["profile"])
service_router.include_router(resume.router, prefix="/resume", tags=["resume"])
service_router.include_router(settings.router, prefix="/settings", tags=["settings"])
service_router.include_router(models.router, prefix="/settings", tags=["settings"])
