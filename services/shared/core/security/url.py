"""URL/SSRF 过滤、DNS pin、安全 HTTP 客户端。

- 多 A 记录遍历 + IPv6 + 端口白名单
- DNS pin：单次解析后固定 IP 建连，缓解 DNS 重绑定 TOCTOU

``_resolve_all`` 及全部策略校验函数保留在本模块（monkeypatch 铁律：测试 patch
``shared.core.security.url._resolve_all``）；pin 三件套在 :mod:`.url_pin`。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx  # noqa: F401 - 保留模块级引用：测试通过 shared.core.security.url.httpx 打补丁

logger = logging.getLogger(__name__)

# 默认拒绝的网段：loopback、link-local、private、CGNAT、multicast、reserved、IPv6 等价
_DEFAULT_BLOCKED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT / 运营商共享
    ipaddress.ip_network("192.0.0.0/24"),  # IANA 特例
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),  # IPv6 multicast
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
]

_LOOPBACK_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

# 允许的对外端口：dev 模式可放行任意；生产期仅 HTTP/HTTPS。
_DEFAULT_ALLOWED_PORTS = frozenset({80, 443})

# 198.18.0.0/15（RFC 2544 benchmark 保留段）：代理 TUN fake-ip 模式会把公网域名
# 解析到该段，TCP 连接由代理接管转发至真实目标，并非真实内网，全局放行。
_PROVIDER_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)
MIMO_TRUSTED_HOSTS = frozenset(
    {
        "api.xiaomimimo.com",
        "token-plan-cn.xiaomimimo.com",
        "token-plan-sgp.xiaomimimo.com",
        "token-plan-ams.xiaomimimo.com",
    }
)


class UnsafeURLError(ValueError):
    """传入的 URL 命中安全策略。"""


def _resolve_all(hostname: str) -> list[ipaddress._BaseAddress]:
    """解析域名/字面量为所有候选 IP。

    - IPv4 / IPv6 字面量直接返回；
    - 域名返回 getaddrinfo 全量 SOCK_STREAM 解析结果。
    """
    try:
        return [ipaddress.ip_address(hostname.strip("[]"))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        raise ValueError(f"无法解析主机: {hostname!r}")
    out: list[ipaddress._BaseAddress] = []
    seen: set[str] = set()
    for info in infos:
        addr = str(info[4][0])
        if addr in seen:
            continue
        seen.add(addr)
        try:
            out.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    return out


def _is_loopback_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(ip in net for net in _LOOPBACK_NETS)


def _ip_is_safe(ip: ipaddress._BaseAddress, *, allow_local: bool) -> bool:
    """单个解析结果是否允许出站。

    ``allow_local=True`` 仅额外放行 loopback；私网 / metadata 仍拒绝。
    fake-ip 段（198.18.0.0/15）无条件放行，见 `_PROVIDER_NETWORKS` 注释。
    """
    if allow_local and _is_loopback_ip(ip):
        return True
    for net in _PROVIDER_NETWORKS:
        if ip in net:
            return True
    for net in _DEFAULT_BLOCKED_NETS:
        if ip in net:
            return False
    try:
        if getattr(ip, "is_private", False):
            return False
        if getattr(ip, "is_multicast", False) or getattr(ip, "is_reserved", False):
            return False
        if getattr(ip, "is_unspecified", False):
            return False
    except Exception:
        pass
    return True


def _all_ips_safe(ips: list[ipaddress._BaseAddress], *, allow_local: bool) -> bool:
    if not ips:
        return False
    return all(_ip_is_safe(ip, allow_local=allow_local) for ip in ips)


def is_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    timeout: float = 3.0,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> bool:
    """校验 ``url`` 是否为安全可外发的 HTTP/HTTPS URL。

    - 仅允许 http(s) 协议；``require_https=True`` 时拒绝 http；
    - 多 A 记录：**任一** 不安全即拒绝；
    - ``allow_local=False`` 时拒绝非常规端口（默认仅 80/443）；
    - ``allow_local=True`` 放行 loopback，私网/metadata 仍拒。
    """
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False
    if require_https and parsed.scheme != "https":
        return False
    if not parsed.hostname:
        return False

    if not allow_local:
        port = parsed.port
        if port is not None and port not in (allowed_ports or _DEFAULT_ALLOWED_PORTS):
            return False

    try:
        ips = _resolve_all(parsed.hostname)
    except ValueError:
        return False
    trusted = trusted_hosts if trusted_hosts is not None else MIMO_TRUSTED_HOSTS
    hostname = parsed.hostname.lower()
    if hostname in trusted:
        return all(
            _ip_is_safe(ip, allow_local=allow_local)
            or any(ip in network for network in _PROVIDER_NETWORKS)
            for ip in ips
        )
    return _all_ips_safe(ips, allow_local=allow_local)


def assert_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> None:
    """不安全时抛出 :class:`UnsafeURLError`。"""
    if not is_safe_http_url(
        url,
        allow_local=allow_local,
        require_https=require_https,
        allowed_ports=allowed_ports,
        trusted_hosts=trusted_hosts,
    ):
        raise UnsafeURLError(f"URL 被策略拒绝: {url!r}")


def pin_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> "PinnedHttpTarget":
    """单次 DNS 解析 → 校验全部候选 → pin 首个安全 IP。"""
    if not url:
        raise UnsafeURLError("URL 为空")
    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        raise UnsafeURLError(f"URL 解析失败: {url!r}") from e

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"URL 协议不安全: {url!r}")
    if require_https and parsed.scheme != "https":
        raise UnsafeURLError(f"生产环境要求 HTTPS: {url!r}")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError(f"URL 缺少主机名: {url!r}")

    if not allow_local:
        port = parsed.port
        if port is not None and port not in (allowed_ports or _DEFAULT_ALLOWED_PORTS):
            raise UnsafeURLError(f"URL 端口不被允许: {url!r}")

    try:
        ips = _resolve_all(hostname)
    except ValueError as e:
        raise UnsafeURLError(str(e)) from e
    if not ips:
        raise UnsafeURLError(f"无法解析主机: {hostname!r}")
    trusted = trusted_hosts if trusted_hosts is not None else MIMO_TRUSTED_HOSTS
    hostname_key = hostname.lower()
    ips_safe = _all_ips_safe(ips, allow_local=allow_local)
    if hostname_key in trusted:
        ips_safe = all(
            _ip_is_safe(ip, allow_local=allow_local)
            or any(ip in network for network in _PROVIDER_NETWORKS)
            for ip in ips
        )
    if not ips_safe:
        raise UnsafeURLError(f"URL 被策略拒绝: {url!r}")

    return PinnedHttpTarget(
        original_url=url.strip(),
        hostname=hostname,
        pinned_ip=str(ips[0]),
        scheme=parsed.scheme,
        port=parsed.port,
    )


def is_localhost_family(host: str) -> bool:
    """判断主机是否位于私有网段（用于限流信任代理链）。"""
    if not host:
        return False
    try:
        ips = _resolve_all(host)
    except ValueError:
        return False
    for ip in ips:
        for net in _DEFAULT_BLOCKED_NETS:
            if ip in net:
                return True
    return False


# pin 部分拆至 url_pin.py；保持 ``shared.core.security.url.*`` 两条 import 路径均可
# （有意再导出：security/__init__ 与测试经本模块取这些符号）
from .url_pin import (  # noqa: E402, F401
    PinnedHostTransport,
    PinnedHttpTarget,
    make_pinned_async_client,
)
