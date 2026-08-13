"""统一异常 handler + envelope 构造。

设计原则：
- main.py 仅做注册路由（@app.exception_handler + handler 函数），
  任何 envelope/spec/headers 处理都收口在本模块；
- 5 个 handler 共用一个 envelope pipeline，单一真相。
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.core.constants import TRACE_ID_HEADER
from shared.core.errors import CATALOG, ErrorSpec
from shared.core.logging import get_trace_id
from shared.core.security import UnsafeURLError

logger = logging.getLogger(__name__)

# ── envelope 构造器 ──────────────────────────────────────

def _trace_id() -> str:
    return get_trace_id() or ""


def _envelope(
    *,
    code: str,
    message: str,
    status: int,
    hint: str = "",
    retryable: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    """构造统一 envelope；自动写 trace_id 与 extra_headers。"""
    resp = JSONResponse(
        status_code=status,
        content={
            "detail": message,
            "error": {
                "code": code,
                "message": message,
                "hint": hint,
                "retryable": retryable,
                "trace_id": _trace_id(),
            },
        },
    )
    tid = get_trace_id()
    if tid:
        resp.headers[TRACE_ID_HEADER] = tid
    for k, v in (extra_headers or {}).items():
        resp.headers[k] = v
    return resp


def _envelope_spec(
    spec: ErrorSpec,
    *,
    message: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    """用 ErrorSpec 全字段构造 envelope；message 缺省用 spec 默认文案。"""
    return _envelope(
        code=spec.code,
        message=message or spec.message,
        status=spec.http_status,
        hint=spec.hint,
        retryable=spec.retryable,
        extra_headers=extra_headers,
    )


# ── HTTPException → envelope 统一翻译器 ──

def _detail_str(exc: Exception) -> str:
    """HTTPException.detail 可能是 str 或 list/dict，统一转 str。"""
    detail = getattr(exc, "detail", "")
    return detail if isinstance(detail, str) else str(detail)


def _exc_headers(exc: Exception) -> dict[str, str]:
    return dict(getattr(exc, "headers", None) or {})


def _envelope_from_http_exception(exc: HTTPException) -> JSONResponse:
    """所有 HTTPException（FastAPI 与 Starlette 共用）走这里。

    - ApiBusinessError（携带 error_code）→ 业务码 + spec 默认文案/hint；
    - 普通 HTTPException → http_{status} 兜底码；
    - 404 优先映射到 A0404（资源不存在）。
    """
    detail = _detail_str(exc)
    extra = _exc_headers(exc)
    # 业务码优先（ApiBusinessError）
    biz_code = getattr(exc, "error_code", None)
    if biz_code and biz_code in CATALOG:
        spec = CATALOG[biz_code]
        return _envelope_spec(spec, message=detail, extra_headers=extra)
    # 404 映射 A0404
    if exc.status_code == 404:
        return _envelope_spec(CATALOG["A0404"], message=detail or "Not Found", extra_headers=extra)
    # 兜底 http_{status}
    return _envelope(
        code=f"http_{exc.status_code}",
        message=detail or "Not Found",
        status=exc.status_code,
        extra_headers=extra,
    )


# ── 5 个 handler 路由 ──

async def on_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("请求校验失败: %s path=%s", exc.errors(), request.url.path)
    return _envelope_spec(CATALOG["A0001"])


async def on_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    return _envelope_from_http_exception(exc)


async def on_starlette_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _envelope_from_http_exception(exc)  # type: ignore[arg-type]


async def on_unsafe_url(request: Request, exc: UnsafeURLError) -> JSONResponse:
    logger.warning("URL 校验失败: %s path=%s", exc, request.url.path)
    return _envelope_spec(CATALOG["A0007"])


async def on_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常 path=%s: %s", request.url.path, exc)
    return _envelope_spec(CATALOG["B0001"], message="服务器内部错误，请稍后重试")


__all__ = [
    "on_http_exception",
    "on_request_validation",
    "on_starlette_http_exception",
    "on_unsafe_url",
    "on_unhandled_exception",
]
