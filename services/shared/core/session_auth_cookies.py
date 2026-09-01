"""会话 Cookie 工具：命名 / 写入 / 清除 / Secure 判定。

从 ``session_auth`` 拆出，公开符号仍由 ``session_auth`` 统一导出。
"""

from __future__ import annotations

from typing import Literal

from fastapi import Request, Response

from shared.config import get_settings

CookieScope = Literal["iv", "prep"]
COOKIE_MAX_AGE = 7 * 24 * 3600


def _peer_is_trusted_proxy(peer: str) -> bool:
    """直连对端是否落在可信代理 CIDR（与限流模块语义一致）。"""
    from shared.core.ratelimit import _peer_is_trusted_proxy as _rl_peer

    return _rl_peer(peer)


def cookie_name(scope: CookieScope, session_id: int) -> str:
    """构造会话 cookie 名。"""
    return f"{scope}_{int(session_id)}"


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
