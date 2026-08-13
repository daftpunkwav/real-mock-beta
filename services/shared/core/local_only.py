"""本机管理 API 访问加固。

档案 / 简历 / 设置等本地管理接口默认仅允许 loopback 对端，
避免 ``HOST=0.0.0.0`` 时被局域网任意客户端改写 BYOK 配置。
"""

from __future__ import annotations

import ipaddress
import os

from fastapi import Request

from shared.config import get_settings
from shared.core.errors import raise_error


def require_local_peer(request: Request) -> None:
    """仅允许 loopback 直连；否则 403。

    Starlette TestClient 的 peer 为 ``testclient``，始终放行。
    ``TEST_MODE=1`` 仅在非生产环境放行真实 HTTP；
    ``env=prod`` 时忽略该开关，防止误部署绕过。
    """
    peer = request.client.host if request.client else None
    if not peer:
        raise_error("A0405")
    assert peer is not None  # 上方 raise_error 不返回 NoReturn，mypy 需要窄化
    if peer == "testclient":
        return
    if (
        os.environ.get("TEST_MODE") == "1"
        and not get_settings().is_prod
    ):
        return
    try:
        ip = ipaddress.ip_address(peer.strip("[]"))
    except ValueError as e:
        raise_error("A0405", cause=e)
    if not ip.is_loopback:
        raise_error("A0405")
