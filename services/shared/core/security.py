"""应用层安全辅助。

集中放置所有安全相关的工具函数，便于在多个路由/服务中复用：

- 文件名清洗（防路径穿越）
- MIME 类型嗅探
- URL/SSRF 过滤（多 A 记录遍历 + IPv6 + 端口白名单）
- DNS pin：单次解析后固定 IP 建连，缓解 DNS 重绑定 TOCTOU
- API Key 脱敏（覆盖主流形态）
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ── 文件名 ────────────────────────────────────────

# 只保留 ASCII 字母数字 + 常见分隔符，其他替换为下划线
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LEN = 120


def sanitize_filename(name: str) -> str:
    """清洗文件名，仅保留安全字符。

    - 取最后一个路径分隔符之后的纯文件名
    - 去除不可打印/控制字符
    - 仅保留 [A-Za-z0-9._-]
    - 长度上限 120
    """
    if not name:
        return "file"

    # 去掉路径部分（Windows / POSIX）
    base = name.replace("\\", "/").split("/")[-1]
    base = base.strip().strip(".") or "file"
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    # 防止仅剩 "."
    if not cleaned or set(cleaned) <= {"."}:
        cleaned = "file"
    if len(cleaned) > _MAX_FILENAME_LEN:
        stem, dot, suffix = cleaned.rpartition(".")
        if dot:
            stem = stem[: _MAX_FILENAME_LEN - len(suffix) - 1]
            cleaned = f"{stem}.{suffix}"
        else:
            cleaned = cleaned[:_MAX_FILENAME_LEN]
    return cleaned


def assert_within_dir(path: Path, root: Path) -> Path:
    """确保 ``path`` 在 ``root`` 之下（路径穿越防御）。

    返回规范化后的路径；越界时抛出 ``ValueError``。
    """
    root_resolved = root.resolve()
    path_resolved = (root_resolved / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"路径越界: {path}") from exc
    return path_resolved


# ── URL / SSRF ────────────────────────────────────

# 默认拒绝的网段：loopback、link-local、private、CGNAT、multicast、reserved、IPv6 等价
_DEFAULT_BLOCKED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT / 运营商共享
    ipaddress.ip_network("192.0.0.0/24"),  # IANA 特例（192.0.0.9/10 PCP anycast 非 is_private）
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),  # IPv6 multicast
    # IPv4-mapped IPv6（攻击者常用绕路）
    ipaddress.ip_network("::ffff:0:0/96"),
]

_LOOPBACK_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

# 允许的对外端口：dev 模式可放行任意；生产期仅 HTTP/HTTPS。
_DEFAULT_ALLOWED_PORTS = frozenset({80, 443})

# 运行环境的 DNS 代理可能把部分国内公网服务解析到 198.18.0.0/15。
# 该网段本身仍然禁止直接访问，只有明确列出的供应商主机名可以使用它。
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
        # IPv4 / IPv6 字面量（如 1.2.3.4 或 ::1）
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
        # getaddrinfo 返回的 addr 可能是 bytes(仅当 nodename 为 bytes 时)，统一转 str
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
    必须对全部 A/AAAA 分别判定（禁止「首个 loopback 即放行」）。
    """
    if allow_local and _is_loopback_ip(ip):
        return True
    for net in _DEFAULT_BLOCKED_NETS:
        if ip in net:
            return False
    # 额外属性：private / reserved / multicast（覆盖未列入显式网段的边界情况）
    # 注意：127.0.0.1 等 loopback 的 is_private 亦为 True，但已在上方
    # allow_local 早退中处理，此处私有判定不会误伤 dev 模式放行。
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

    .. note::

        仅做校验不建连。出站请用 :func:`pin_safe_http_url`
        （单次解析 → 校验 → pin，禁止二次 DNS）。
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


@dataclass(frozen=True)
class PinnedHttpTarget:
    """SSRF 校验通过后锁定的连接目标。

    - ``hostname``: 原始主机名（Host / SNI）
    - ``pinned_ip``: **同一次**解析中校验通过的安全 IP
    """

    original_url: str
    hostname: str
    pinned_ip: str
    scheme: str
    port: int | None


def pin_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> PinnedHttpTarget:
    """单次 DNS 解析 → 校验全部候选 → pin 首个安全 IP。

    **禁止**先 ``is_safe_http_url`` 再二次 ``_resolve_all``，否则存在
    DNS 重绑定 TOCTOU（校验时公网、pin 时内网）。
    """
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


class PinnedHostTransport(httpx.AsyncBaseTransport):
    """将请求中的主机名改写为已 pin 的 IP，并保留 Host / SNI。

    建连路径使用 IP 字面量，不再触发 DNS 二次解析，从而缓解经典 DNS 重绑定。
    """

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
        # 仅改写匹配 pin 的主机；其它透传（防御误用）
        if not host or host.lower() not in {
            self._hostname.lower(),
            self._pinned_ip.lower().strip("[]"),
        }:
            return await self._inner.handle_async_request(request)

        # httpx 0.28 Headers 无 mutablecopy，复制为新 Headers
        headers = httpx.Headers(request.headers)
        port = request.url.port
        if port and port not in (80, 443):
            headers["host"] = f"{self._hostname}:{port}"
        else:
            headers["host"] = self._hostname

        new_url = request.url.copy_with(host=self._pinned_ip)
        extensions = dict(request.extensions or {})
        # httpcore：SNI + 证书校验主机名使用原始域名，而非 IP
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
    """创建对 ``url`` 主机做 DNS pin 的 :class:`httpx.AsyncClient`。

    请求仍使用原始 URL（含 hostname），由 transport 在出站时改写为 pin IP。
    """
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
    # 禁止跟随重定向：跳转目标可能脱离 pin 主机
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
    )


def is_localhost_family(host: str) -> bool:
    """判断主机（IP 字面量或域名解析后）是否位于私有网段（用于限流信任代理链）。"""
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


# ── API Key 脱敏 ──────────────────────────────────


# 各家厂商前缀集合
_API_KEY_PREFIXES = (
    "sk-",        # OpenAI / StepFun / 通用
    "sk_",        # 部分国内供应商
    "sk-ant-",    # Anthropic
    "aiza",       # Google (AIza...)
    "step-",      # StepFun
)


def _looks_like_api_key(v: str) -> bool:
    lowered = v.lower()
    if lowered.startswith("aiza"):
        return True
    if v.startswith("sk-ant-"):
        return True
    return v.startswith("sk-") or v.startswith("sk_")


def _looks_like_secret(v: str) -> bool:
    """启发式：判断字符串是否像秘密（API Key、token、UUID 等）。

    启发规则：

    - 长度需 ``>= 20``（一般 API Key 远长于此）；
    - 至少有 ASCII 字母 / 数字出现；
    - 同时包含字母与数字（避免普通短语被误判）；
    - 不包含空格（避免截断错误）。
    """
    if len(v) < 20 or " " in v:
        return False
    has_letter = any(c.isalpha() for c in v)
    has_digit = any(c.isdigit() for c in v)
    return has_letter and has_digit


def redact_api_key(value: str | None) -> str:
    """用于日志输出的 API Key 脱敏。

    同时覆盖:
    - 各家 Key（OpenAI/Anthropic/Google/StepFun）；
    - ``Authorization: Bearer xxxx`` / ``authorization=xxxx`` 头形式；
    - PEM 私钥块（含换行）；
    - 启发式认为"长度足够 + 字母数字混合 + 无空格"的 token。

    普通短语、日志模板（``HTTP/%s ...``）不会被误判。
    """
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        # 短字符串默认不脱敏，避免误伤中文短语/路径/短 token 自身
        return v

    # PEM / 证书块：含换行，启发式会漏掉
    if "-----BEGIN" in v.upper():
        return "***PEM_REDACTED***"

    # Authorization / authorization=xxx 形式：只保留 scheme，后续 token 整体遮蔽
    lowered = v.lower()
    if lowered.startswith("authorization"):
        scheme_idx = v.find(":") if ":" in v else v.find("=")
        if scheme_idx >= 0:
            head = v[: scheme_idx + 1]
            return f"{head} ***"
        return "Authorization ***"

    # 显式 Bearer / Token 前缀
    for prefix in ("bearer ", "token ", "basic "):
        if lowered.startswith(prefix):
            return f"{prefix[:1].upper()}{prefix[1:]}***"

    if _looks_like_api_key(v):
        return f"{v[:4]}***{v[-4:]}"

    # 启发式 secret（如不规则 token / UUID）才走"首尾 4 字符"脱敏
    if _looks_like_secret(v):
        return f"{v[:4]}***{v[-4:]}"

    return v
