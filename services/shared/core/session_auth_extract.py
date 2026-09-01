"""会话能力令牌提取：HTTP（Header > Cookie > query）与 WebSocket。

从 ``session_auth`` 拆出，公开符号仍由 ``session_auth`` 统一导出。
"""

from __future__ import annotations

import logging

from fastapi import Header, Query, Request, WebSocket

from shared.config import get_settings
from shared.core.session_auth_cookies import CookieScope, cookie_name
from shared.core.session_auth_csrf import _assert_csrf_if_cookie_only

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Interview-Token"
# WebSocket 子协议前缀：mock.<token>（token 已为 url-safe）
WS_SUBPROTOCOL_PREFIX = "mock."


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
