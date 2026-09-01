"""会话能力令牌（capability token）。

本地优先产品不引入多用户登录；对可变操作（WS / start / message / finish /
messages / reports / prep）要求创建时下发的 ``access_token``，防止仅凭整数
session_id 劫持。

默认经 HttpOnly Cookie 下发（``iv_{id}`` / ``prep_{id}``）；
仍兼容 ``X-Interview-Token`` Header（测试与迁移）。
生产环境拒绝 query ``?token=``，避免代理/访问日志泄漏。

实现按职责拆到同目录子模块，本模块统一导出公开符号：

- ``session_auth_tokens``：生成 / 常量时间比较 / 断言
- ``session_auth_cookies``：cookie 命名 / 写入 / 清除 / Secure 判定
- ``session_auth_extract``：HTTP / WebSocket 令牌提取
- ``session_auth_csrf``：cookie-only CSRF / Origin 校验
"""

from __future__ import annotations

from shared.core.session_auth_cookies import (
    COOKIE_MAX_AGE,
    CookieScope,
    clear_session_cookie,
    cookie_name,
    cookie_should_be_secure,
    set_session_cookie,
)
from shared.core.session_auth_extract import (
    HEADER_NAME,
    WS_SUBPROTOCOL_PREFIX,
    _extract_from_request,
    extract_prep_token,
    extract_token,
    extract_ws_token,
    ws_token_subprotocol,
)
from shared.core.session_auth_tokens import (
    HasAccessToken,
    assert_session_token,
    new_access_token,
    tokens_match,
)

__all__ = [
    "HEADER_NAME",
    "WS_SUBPROTOCOL_PREFIX",
    "COOKIE_MAX_AGE",
    "CookieScope",
    "HasAccessToken",
    "cookie_name",
    "new_access_token",
    "tokens_match",
    "assert_session_token",
    "cookie_should_be_secure",
    "set_session_cookie",
    "clear_session_cookie",
    "extract_token",
    "extract_prep_token",
    "extract_ws_token",
    "ws_token_subprotocol",
    "_extract_from_request",
]
