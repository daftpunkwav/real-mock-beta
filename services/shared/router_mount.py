"""聚合入口路由挂载：统一 /api/v1 与 /api 兼容别名，避免 main 双份复制。"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, FastAPI


def include_service_routers(app: FastAPI, routers: Sequence[APIRouter], prefix: str) -> None:
    """将多个服务 router 挂到同一 API 前缀下。"""
    for router in routers:
        app.include_router(router, prefix=prefix)


def include_with_legacy_api_alias(
    app: FastAPI,
    routers: Sequence[APIRouter],
    *,
    versioned_prefix: str = "/api/v1",
    legacy_prefix: str = "/api",
) -> None:
    """挂载版本化前缀，并额外注册 legacy 前缀（滚动兼容期）。"""
    include_service_routers(app, routers, versioned_prefix)
    legacy = APIRouter()
    for router in routers:
        legacy.include_router(router, prefix=legacy_prefix)
    app.include_router(legacy)
