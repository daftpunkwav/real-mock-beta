"""服务应用工厂：统一三服务的 FastAPI app 构造。

三服务(api_service / agent_service / interview_service)的独立入口共享相同的
CORS / health / 路由前缀装配逻辑,本工厂消除字面复制。聚合入口(services.main)
叠加额外中间件(trace / 门禁 / 别名 / 异常 handler)后复用同一工厂。
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from shared.core.constants import TRACE_ID_HEADER


def create_service_app(
    *,
    service_router: APIRouter,
    title: str,
    description: str,
    service_name: str,
    lifespan_startup: Callable[[], Any] | None = None,
) -> FastAPI:
    """构造一个服务 FastAPI app(CORS + health + /api/v1 路由)。

    Args:
        service_router: 服务的纯路由聚合(无前缀,由本函数注入 /api/v1)
        title: FastAPI title
        description: FastAPI description
        service_name: /health 返回的 service 字段(如 "api-service")
        lifespan_startup: 可选的异步启动钩子(建表/迁移/RAG 等);TEST_MODE=1 时跳过
    """
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import os

        if os.environ.get("TEST_MODE") == "1":
            yield
            return
        if lifespan_startup is not None:
            import inspect

            result = lifespan_startup()
            if inspect.isawaitable(result):
                await result
        yield

    app = FastAPI(
        title=title,
        description=description,
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id", TRACE_ID_HEADER, "X-Interview-Token"],
        expose_headers=[TRACE_ID_HEADER],
        max_age=600,
    )
    app.include_router(service_router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": service_name, "version": "1.0.0"}

    return app
