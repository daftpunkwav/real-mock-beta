"""服务应用工厂：统一各服务的 FastAPI app 构造。

三服务(api_service / agent_service / interview_service)的独立入口共享相同的
CORS / health / 路由前缀 / 异常 handler / trace_id 装配逻辑，本工厂消除字面复制。

每个服务经本工厂构造的 app 都具备「可独立成进程运行」的完整装配：

- 统一异常 handler（错误响应走同一 envelope）；
- trace_id 注入中间件（每个进程都有可观测性）；
- CORS / health / ``/api/v1`` 前缀；
- 支持单个或多个 router（为未来「多服务合并一进程」预留）。

聚合入口(services.main)有自己更重的装配(生产门禁 / ``/api`` 兼容别名)，
保持独立实现，不复用本工厂——两者各自挂载互不干扰。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.config import get_settings
from shared.core.constants import TRACE_ID_HEADER
from shared.core.error_handlers import (
    on_http_exception,
    on_request_validation,
    on_starlette_http_exception,
    on_unhandled_exception,
    on_unsafe_url,
)
from shared.core.logging import get_trace_id, reset_trace_id, set_trace_id
from shared.core.security import UnsafeURLError

logger = logging.getLogger(__name__)

# X-Request-Id 校验：仅允许 [A-Za-z0-9_-]{8,64}。其他字符 / 过短 / 过长一律
# 重新生成，防止日志注入（CRLF / 控制字符）。与聚合入口保持同一规则。
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")


def _sanitize_request_id(raw: str | None) -> str | None:
    """校验通过返回原值，否则返回 None（由 set_trace_id 重新生成）。"""
    if raw and _REQUEST_ID_RE.match(raw):
        return raw
    return None


def create_service_app(
    *,
    service_routers: APIRouter | Sequence[APIRouter],
    title: str,
    description: str,
    service_name: str,
    lifespan_startup: Callable[[], Any] | None = None,
    register_error_handlers: bool = True,
    enable_trace: bool = True,
) -> FastAPI:
    """构造一个服务 FastAPI app(CORS + health + /api/v1 路由 + 异常 handler + trace)。

    Args:
        service_routers: 服务的纯路由聚合(无前缀，由本函数注入 /api/v1)；
            支持单个 ``APIRouter`` 或多个(为多服务合并一进程预留)。
        title: FastAPI title
        description: FastAPI description
        service_name: ``/health`` 返回的 service 字段(如 "api-service")
        lifespan_startup: 可选启动钩子(建表/迁移/RAG 等)；TEST_MODE=1 时跳过
        register_error_handlers: 注册统一异常 handler(默认 True)，保证独立进程
            的错误响应走统一 envelope
        enable_trace: 注入 trace_id 中间件(默认 True)，保证独立进程有可观测性
    """
    settings = get_settings()

    # 归一化 router 列表（兼容单个 APIRouter 与多个）
    routers: list[APIRouter] = (
        [service_routers]
        if isinstance(service_routers, APIRouter)
        else list(service_routers)
    )

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

    if enable_trace:

        @app.middleware("http")
        async def trace_middleware(request: Request, call_next):
            """为每个 HTTP 请求注入 trace_id，便于日志串联。"""
            raw = request.headers.get("x-request-id") or request.headers.get("X-Request-Id")
            token = set_trace_id(_sanitize_request_id(raw))
            response_trace_id = get_trace_id()
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("HTTP 中间件异常 path=%s", request.url.path)
                raise
            finally:
                reset_trace_id(token)
            response.headers[TRACE_ID_HEADER] = response_trace_id or ""
            return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id", TRACE_ID_HEADER, "X-Interview-Token"],
        expose_headers=[TRACE_ID_HEADER],
        max_age=600,
    )

    for r in routers:
        app.include_router(r, prefix="/api/v1")

    if register_error_handlers:
        app.add_exception_handler(RequestValidationError, on_request_validation)  # type: ignore[arg-type]
        app.add_exception_handler(HTTPException, on_http_exception)  # type: ignore[arg-type]
        app.add_exception_handler(StarletteHTTPException, on_starlette_http_exception)  # type: ignore[arg-type]
        app.add_exception_handler(UnsafeURLError, on_unsafe_url)  # type: ignore[arg-type]
        app.add_exception_handler(Exception, on_unhandled_exception)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": service_name, "version": "1.0.0"}

    return app
