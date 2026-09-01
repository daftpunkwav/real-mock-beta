"""cookie-only CSRF 缓解：Origin / Referer 白名单校验。

从 ``session_auth`` 拆出；``_extract_from_request`` 在 cookie-only 鉴权路径
调用 :func:`_assert_csrf_if_cookie_only`。
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from shared.config import get_settings
from shared.core.errors import raise_error


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
