"""会话能力令牌（capability token）。

本地优先产品不引入多用户登录；对可变操作（WS / start / message / finish /
messages / reports / prep）要求创建时下发的 ``access_token``，防止仅凭整数
session_id 劫持。

默认经 HttpOnly Cookie 下发（``iv_{id}`` / ``prep_{id}``）；
仍兼容 ``X-Interview-Token`` Header（测试与迁移）。
生产环境拒绝 query ``?token=``，避免代理/访问日志泄漏。
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from fastapi import Header, Query, Request, Response, WebSocket

from shared.config import get_settings
from shared.core.errors import ApiBusinessError, get_spec, raise_error

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Interview-Token"
# WebSocket 子协议前缀：mock.<token>（token 已为 url-safe）
WS_SUBPROTOCOL_PREFIX = "mock."

CookieScope = Literal["iv", "prep"]
COOKIE_MAX_AGE = 7 * 24 * 3600


class HasAccessToken(Protocol):
    access_token: Any


def cookie_name(scope: CookieScope, session_id: int) -> str:
    """构造会话 cookie 名。"""
    return f"{scope}_{int(session_id)}"


def new_access_token() -> str:
    """生成会话能力令牌（url-safe，约 32 字节熵）。"""
    return secrets.token_urlsafe(32)


def tokens_match(expected: str | None, provided: str | None) -> bool:
    """常量时间比较；任一侧为空则拒绝。"""
    exp = (expected or "").strip()
    got = (provided or "").strip()
    if not exp or not got:
        return False
    if len(exp) != len(got):
        # compare_digest 要求等长；长度不等直接拒绝（仍避免短路泄漏具体内容）
        secrets.compare_digest(exp, exp)
        return False
    return secrets.compare_digest(exp, got)


def assert_session_token(
    session: HasAccessToken,
    provided: str | None,
    *,
    detail: str = "无权访问该面试会话",
) -> None:
    """校验失败抛 403。"""
    if not tokens_match(getattr(session, "access_token", None), provided):
        raise ApiBusinessError(get_spec("A0401"), message=detail)


def _peer_is_trusted_proxy(peer: str) -> bool:
    """直连对端是否落在可信代理 CIDR（与限流模块语义一致）。"""
    from shared.core.ratelimit import _peer_is_trusted_proxy as _rl_peer

    return _rl_peer(peer)


def cookie_should_be_secure(request: Request) -> bool:
    """是否为会话 Cookie 设置 Secure。

    - ``COOKIE_SECURE=true/false`` 显式覆盖；
    - 否则：请求 scheme 为 https，或可信代理且 ``X-Forwarded-Proto=https``。
    """
    settings = get_settings()
    if settings.cookie_secure is True:
        return True
    if settings.cookie_secure is False:
        return False
    if request.url.scheme == "https":
        return True
    peer = request.client.host if request.client else None
    if peer and _peer_is_trusted_proxy(peer):
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        if proto == "https":
            return True
    return False


def set_session_cookie(
    response: Response,
    *,
    scope: CookieScope,
    session_id: int,
    token: str,
    secure: bool,
) -> None:
    """写入 HttpOnly 会话 cookie。"""
    response.set_cookie(
        key=cookie_name(scope, session_id),
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_session_cookie(
    response: Response,
    *,
    scope: CookieScope,
    session_id: int,
) -> None:
    response.delete_cookie(key=cookie_name(scope, session_id), path="/")


def _origin_allowed(request: Request) -> bool:
    """校验 Origin/Referer 是否落在 CORS 白名单（cookie 鉴权 CSRF 缓解）。"""
    allowed = {o.rstrip("/") for o in get_settings().cors_origin_list}
    if not allowed:
        return False
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin and origin in allowed:
        return True
    referer = (request.headers.get("referer") or "").strip()
    if referer:
        try:
            parsed = urlparse(referer)
            ref_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            if ref_origin in allowed:
                return True
        except Exception:
            pass
    return False


def _assert_csrf_if_cookie_only(
    request: Request,
    *,
    used_header: bool,
) -> None:
    """仅 cookie 鉴权时要求 Origin/Referer；Header 令牌视为显式能力（测试友好）。"""
    if used_header:
        return
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return
    if not _origin_allowed(request):
        raise_error("A0403")


def _extract_from_request(
    request: Request,
    *,
    scope: CookieScope,
    session_id: int,
    x_interview_token: str | None,
    token: str | None,
) -> str | None:
    cookie_tok = (request.cookies.get(cookie_name(scope, session_id)) or "").strip()
    header_tok = (x_interview_token or "").strip()
    query_tok = (token or "").strip()
    if query_tok and get_settings().is_prod:
        logger.warning("生产环境拒绝 HTTP query token path=%s", request.url.path)
        query_tok = ""
    used_header = bool(header_tok)
    chosen = header_tok or cookie_tok or query_tok or None
    if chosen and cookie_tok and not header_tok:
        _assert_csrf_if_cookie_only(request, used_header=False)
    elif chosen and not header_tok and not cookie_tok:
        # 仅 query：同样要求 CSRF（防 token 落日志后被跨站利用）
        _assert_csrf_if_cookie_only(request, used_header=False)
    elif chosen and used_header:
        pass
    return chosen or None


def extract_token(
    session_id: int,
    request: Request,
    x_interview_token: str | None = Header(default=None, alias=HEADER_NAME),
    token: str | None = Query(default=None, description="会话能力令牌（兼容；prod 禁用）"),
) -> str | None:
    """面试 / 报告 HTTP 依赖：Header > Cookie > query（prod 无 query）。"""
    return _extract_from_request(
        request,
        scope="iv",
        session_id=session_id,
        x_interview_token=x_interview_token,
        token=token,
    )


def extract_prep_token(
    session_id: int,
    request: Request,
    x_interview_token: str | None = Header(default=None, alias=HEADER_NAME),
    token: str | None = Query(default=None, description="Prep 能力令牌（兼容；prod 禁用）"),
) -> str | None:
    """Prep HTTP 依赖。"""
    return _extract_from_request(
        request,
        scope="prep",
        session_id=session_id,
        x_interview_token=x_interview_token,
        token=token,
    )


def ws_token_subprotocol(token: str) -> str:
    """构造携带令牌的 WebSocket 子协议名。"""
    return f"{WS_SUBPROTOCOL_PREFIX}{(token or '').strip()}"


def extract_ws_token(
    websocket: WebSocket,
    *,
    session_id: int | None = None,
    query_token: str | None = None,
) -> tuple[str, str | None]:
    """从 WS 握手提取能力令牌。

    优先级：
    1. Cookie ``iv_{session_id}``（HttpOnly，同源/直连后端）
    2. ``Sec-WebSocket-Protocol: mock.<token>``（兼容）
    3. query ``token=``（仅非生产；生产忽略以防日志泄漏）

    Returns:
        ``(access_token, chosen_subprotocol_or_None)``
        若使用了子协议传令牌，第二项为完整子协议字符串，供 ``accept(subprotocol=...)``。
    """
    if session_id is not None:
        cookie_tok = (websocket.cookies.get(cookie_name("iv", session_id)) or "").strip()
        if cookie_tok:
            return cookie_tok, None

    header = websocket.headers.get("sec-websocket-protocol") or ""
    for part in header.split(","):
        p = part.strip()
        if not p:
            continue
        if p.lower().startswith(WS_SUBPROTOCOL_PREFIX):
            tok = p[len(WS_SUBPROTOCOL_PREFIX) :].strip()
            if tok:
                return tok, p
    q = (query_token or "").strip()
    if q and get_settings().is_prod:
        logger.warning("生产环境拒绝 WebSocket query token")
        return "", None
    return q, None
