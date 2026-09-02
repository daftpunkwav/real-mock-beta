"""RealMock 后端聚合入口（模块化单体单进程形态）。

组合三个服务的 ``service_router`` 为一个 FastAPI app：

- api_service：档案 / 简历 / 处理器配置
- agent_service：面试准备教练
- interview_service：模拟面试引擎 / 实时 WebSocket / 报告 / 成长

运行：``uvicorn services.main:app --port 8081``（从仓库根，PYTHONPATH=services 由 pyproject 注入）
三个服务亦可独立启动（见各服务 ``main.py``），此时本聚合入口即微服务网关的雏形。

集中管理：

- CORS 严格策略：通配 origins 与 credentials=True 同时启用将启动失败；
- trace_id 注入 + 校验：合法 X-Request-Id 沿用，否则重新生成；
- lifespan：同步 IO 走 ``asyncio.to_thread`` 不阻塞事件循环；
- 统一错误响应信封。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from api_service.router import service_router as api_router
from agent_service.router import service_router as agent_router
from interview_service.router import service_router as interview_router
from interview_service.startup import ensure_rag_index
from shared.config import Settings, get_settings
from shared.core.logging import (
    configure_logging,
    get_trace_id,
    reset_trace_id,
    set_trace_id,
)
from shared.core.error_handlers import (
    on_http_exception,
    on_request_validation,
    on_starlette_http_exception,
    on_unsafe_url,
    on_unhandled_exception,
)
from shared.core.constants import TRACE_ID_HEADER
from shared.core.security import UnsafeURLError
from shared.database import dispose_all_engines
from shared.router_mount import include_with_legacy_api_alias
from bootstrap.db_bootstrap import bootstrap_databases_and_seed

configure_logging()
logger = logging.getLogger(__name__)

# 三服务纯路由（无前缀）；聚合入口统一挂载 /api/v1 与 /api 兼容别名
SERVICE_ROUTERS = (api_router, agent_router, interview_router)


# ── X-Request-Id 校验 ────────────────────────────────────────
# 仅允许 [A-Za-z0-9_-]{8,64}。其他字符 / 过短 / 过长一律重新生成，
# 防止日志注入（CRLF / 控制字符）。
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")


def _sanitize_request_id(raw: str | None) -> str | None:
    """校验通过返回原值，否则返回 None（由 set_trace_id 重新生成）。"""
    if raw and _REQUEST_ID_RE.match(raw):
        return raw
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭钩子。

    同步 IO（SQLite / 文件系统 / 本地 RAG 构建）统一丢到线程池执行，
    避免阻塞事件循环导致心跳/WS 抖动。
    """
    # 启动：建表 + 迁移 + 处理器配置 seed + 企业知识库 RAG 索引
    if os.environ.get("TEST_MODE") == "1":
        _bootstrap_db_and_seed()
    else:
        await asyncio.to_thread(_bootstrap_db_and_seed)
    await ensure_rag_index()
    cfg = get_settings()
    logger.info("RealMock 后端已启动 env=%s", cfg.env)
    try:
        yield
    finally:
        if not cfg.is_prod and os.environ.get("TEST_MODE") == "1":
            logger.debug("测试模式：跳过 engine dispose")
        else:
            try:
                await asyncio.to_thread(_shutdown_engine)
            except Exception:
                logger.exception("关闭阶段释放引擎失败")
        logger.info("RealMock 后端已关闭")


def _bootstrap_db_and_seed() -> None:
    bootstrap_databases_and_seed()


def _shutdown_engine() -> None:
    """关闭阶段 dispose 双引擎。"""
    try:
        dispose_all_engines()
    except Exception:
        logger.exception("engine.dispose 失败")


def create_app() -> FastAPI:
    """构造聚合 FastAPI app：三服务路由 + 统一中间件/异常处理。"""
    cfg = get_settings()
    app = FastAPI(
        title="RealMock API",
        description="RealMock 模拟面试平台聚合入口（api + agent + interview 三服务）",
        version="1.0.0",
        lifespan=lifespan,
    )

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

    # ── CORS 严格策略 ────────────────────────────────────────
    _check_cors_policy(cfg)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-Id",
            TRACE_ID_HEADER,
            "X-Interview-Token",
        ],
        expose_headers=[TRACE_ID_HEADER],
        max_age=600,
    )

    # ── master key 生产门禁 ────────────────────────────────────────
    _check_secret_key_policy(cfg)

    include_with_legacy_api_alias(app, SERVICE_ROUTERS)

    # ── 统一错误响应形状 ────────────────────────────────────────
    app.add_exception_handler(RequestValidationError, on_request_validation)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, on_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, on_starlette_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(UnsafeURLError, on_unsafe_url)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, on_unhandled_exception)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "realmock", "version": "1.0.0"}

    return app


def _check_cors_policy(s: Settings) -> None:
    """生产环境禁止通配 origins；开发环境允许但打 warning。"""
    if "*" in s.cors_origin_list:
        if s.is_prod:
            raise RuntimeError(
                "CORS 配置非法：生产环境 (env=prod) 不允许 allow_origins=['*']。"
                "请在环境变量 CORS_ORIGINS 中显式列出可信来源。"
            )
        logger.warning("CORS 允许 * 通配，仅 dev 环境；生产环境已强制要求显式来源")


def _check_secret_key_policy(s: Settings) -> None:
    """prod 部署必须显式提供 SECRET_KEY；否则密钥落盘 data/.secret.key，
    数据库从其他机器迁移后 API Key 密文无法解密。"""
    if s.is_prod:
        from shared.core.secrets import validate_master_key_env

        status = validate_master_key_env()
        if status != "ok":
            raise RuntimeError(
                "生产环境 (env=prod) 必须设置 SECRET_KEY（≥16 字节）；"
                "禁止依赖自动生成的 data/.secret.key，否则数据库迁移后密文不可解密。"
            )


app = create_app()


if __name__ == "__main__":
    # 无参启动入口：`python -m services.main` 自动读取 .env 的 HOST / PORT。
    boot = get_settings()
    uvicorn.run(app, host=boot.host, port=boot.port)
