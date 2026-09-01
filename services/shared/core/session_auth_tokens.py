"""会话能力令牌原语：生成 / 常量时间比较 / 断言。

从 ``session_auth`` 拆出，公开符号仍由 ``session_auth`` 统一导出。
"""

from __future__ import annotations

import secrets
from typing import Any, Protocol

from shared.core.errors import ApiBusinessError, get_spec


class HasAccessToken(Protocol):
    access_token: Any


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
