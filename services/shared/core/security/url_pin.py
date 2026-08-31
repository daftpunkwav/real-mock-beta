"""URL DNS pin：单次解析后固定 IP 建连，缓解 DNS 重绑定 TOCTOU。

拆自 :mod:`shared.core.security.url`（monkeypatch 铁律：``_resolve_all`` 及
策略校验函数仍留在 ``url.py``，测试 patch ``url._resolve_all`` 依然命中）。
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Any
# 不要在模块顶层 import url.py：url.py 尾部会再 import 本模块。
# make_pinned_async_client 内延迟取 pin_safe_http_url，避免循环 import。


@dataclass(frozen=True)
class PinnedHttpTarget:
    """SSRF 校验通过后锁定的连接目标。"""

    original_url: str
    hostname: str
    pinned_ip: str
    scheme: str
    port: int | None


class PinnedHostTransport(httpx.AsyncBaseTransport):
    """将请求中的主机名改写为已 pin 的 IP，并保留 Host / SNI。"""

    def __init__(
        self,
        hostname: str,
        pinned_ip: str,
        **transport_kwargs: Any,
    ) -> None:
        self._hostname = hostname
        self._pinned_ip = pinned_ip
        self._inner = httpx.AsyncHTTPTransport(**transport_kwargs)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if not host or host.lower() not in {
            self._hostname.lower(),
            self._pinned_ip.lower().strip("[]"),
        }:
            return await self._inner.handle_async_request(request)

        headers = httpx.Headers(request.headers)
        port = request.url.port
        if port and port not in (80, 443):
            headers["host"] = f"{self._hostname}:{port}"
        else:
            headers["host"] = self._hostname

        new_url = request.url.copy_with(host=self._pinned_ip)
        extensions = dict(request.extensions or {})
        extensions["sni_hostname"] = self._hostname

        pinned_request = httpx.Request(
            method=request.method,
            url=new_url,
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self._inner.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def make_pinned_async_client(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    timeout: float = 60.0,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> httpx.AsyncClient:
    """创建对 ``url`` 主机做 DNS pin 的 :class:`httpx.AsyncClient`。"""
    from .url import pin_safe_http_url

    target = pin_safe_http_url(
        url,
        allow_local=allow_local,
        require_https=require_https,
        allowed_ports=allowed_ports,
        trusted_hosts=trusted_hosts,
    )
    transport = PinnedHostTransport(
        hostname=target.hostname,
        pinned_ip=target.pinned_ip,
    )
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
    )
