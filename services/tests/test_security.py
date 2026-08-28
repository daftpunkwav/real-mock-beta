"""``app.core.security`` 单元测试。

覆盖：
- ``redact_api_key`` 的多种输入形态；
- ``sanitize_filename`` 防路径穿越；
- ``assert_within_dir`` 越界检测；
- ``is_safe_http_url`` SSRF 防御（loopback / 私网 / 链路本地）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from shared.core.security import (
    PinnedHostTransport,
    UnsafeURLError,
    assert_safe_http_url,
    assert_within_dir,
    is_safe_http_url,
    pin_safe_http_url,
    redact_api_key,
    sanitize_filename,
)


# ---------------------------------------------------------------------------
# redact_api_key
# ---------------------------------------------------------------------------


class TestRedactApiKey:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", ""),
            (None, ""),
            # 正常 Key
            ("sk-12345678abcdefgh", "sk-1***efgh"),
            ("sk-proj-abc123def456ghi789", "sk-p***i789"),
            ("sk-verylongapikeywithmanychars", "sk-v***hars"),
            # Authorization / Bearer / Token 形式
            ("authorization: Bearer abc123def456", "authorization: ***"),
            ("Authorization: Bearer abc123def456", "Authorization: ***"),
            ("authorization=abc123def456", "authorization= ***"),
            ("bearer abc123def456", "Bearer ***"),
            ("token abc123def456", "Token ***"),
            ("basic dXNlcjpwYXNz", "Basic ***"),
            # 各家厂商前缀
            ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234", "sk-a***1234"),
            ("AIzaSyAbcDefGhiJklMnoPqrStuVwxYz1234567", "AIza***4567"),
            ("step-3.7-flash-abcdefghijklmnop", "step***mnop"),
            # 短字符串与日常短语不再被误判为 ***
            ("short", "short"),
            ("RAG settings", "RAG settings"),
            ("HTTP/1.1", "HTTP/1.1"),
            # 启发式 secret（>=20 + 字母数字混合）才脱敏
            ("abcdef1234567890abcdef1234567890abcd", "abcd***abcd"),
            # 长句（>8 字符 + 含空格）不被脱敏，避免日志行误伤
            ("this is a long log message", "this is a long log message"),
        ],
    )
    def test_redact_variants(self, raw: str | None, expected: str) -> None:
        assert redact_api_key(raw) == expected

    def test_short_strings_not_overredacted(self) -> None:
        """短字符串（≤8 字符）应原样返回，避免误伤 RAG / hh:mm 等短语。"""
        assert redact_api_key("RAG") == "RAG"
        assert redact_api_key("RAG settings") == "RAG settings"
        assert redact_api_key("main.py") == "main.py"

    def test_secret_shaped_strings(self) -> None:
        """长字符串 + 字母数字混合 + 无空格 走"首尾 4 字符"脱敏。"""
        token = "abcdef1234567890abcdef1234567890abcd"
        assert redact_api_key(token) == "abcd***abcd"

    def test_url_with_credentials(self) -> None:
        """URL 中的 user:password 段不应被错认成 API Key（不脱敏）。"""
        url = "https://user:pass@example.com/api"
        assert redact_api_key(url) == url  # URL 不在内置 Key 形态里

    def test_pem_block_redacted(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC...\n-----END PRIVATE KEY-----"
        assert redact_api_key(pem) == "***PEM_REDACTED***"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "raw,expected_substr",
        [
            ("../../../etc/passwd", "passwd"),
            ("..\\..\\windows\\system32", "system32"),
            ("file with spaces.pdf", "file_with_spaces.pdf"),
            # 中文路径分隔后只剩扩展名,因为仅保留 ASCII 字母数字 + . _ -
            ("中文简历.pdf", ".pdf"),
            ("...hidden", "hidden"),  # 清理 "." 前缀但保留核心内容
            ("", "file"),
            ("\x00evil\x00.exe", "_evil_.exe"),
            ("a" * 200 + ".pdf", ".pdf"),
        ],
    )
    def test_sanitization(self, raw: str, expected_substr: str) -> None:
        result = sanitize_filename(raw)
        assert expected_substr in result
        # 永远不应包含路径分隔符或控制字符
        assert "/" not in result
        assert "\\" not in result
        assert "\x00" not in result


# ---------------------------------------------------------------------------
# assert_within_dir
# ---------------------------------------------------------------------------


class TestAssertWithinDir:
    def test_relative_path_inside(self, tmp_path: Path) -> None:
        p = assert_within_dir(Path("subdir/file.txt"), tmp_path)
        assert p == (tmp_path / "subdir" / "file.txt").resolve()

    def test_relative_path_traversal_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="路径越界"):
            assert_within_dir(Path("../escape.txt"), tmp_path)

    def test_absolute_path_inside(self, tmp_path: Path) -> None:
        inner = tmp_path / "inner.txt"
        inner.write_text("ok")
        resolved = assert_within_dir(inner, tmp_path)
        assert resolved == inner.resolve()

    def test_absolute_path_outside_blocked(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("ok")
        with pytest.raises(ValueError, match="路径越界"):
            assert_within_dir(outside, tmp_path)


# ---------------------------------------------------------------------------
# is_safe_http_url / assert_safe_http_url
# ---------------------------------------------------------------------------


class TestIsSafeHttpUrl:
    @pytest.mark.parametrize(
        "url,allow_local,expected",
        [
            # 协议校验
            ("javascript:alert(1)", False, False),
            ("file:///etc/passwd", False, False),
            ("ftp://example.com", False, False),
            ("", False, False),
            # 公网 https
            ("https://api.openai.com/v1", False, True),
            ("http://api.example.com/v1", False, True),
            # loopback / 私网 在严格模式下拒绝
            ("http://127.0.0.1:8000", False, False),
            ("http://10.0.0.1", False, False),
            ("http://192.168.1.1", False, False),
            ("http://172.16.0.1", False, False),
            ("http://169.254.169.254/latest/meta-data", False, False),
            ("http://[::1]", False, False),
            # 文档 / 基准网段（is_private=True，未列入显式黑名单，靠通用 is_private 拦截）
            ("http://198.18.0.10", False, False),  # RFC 2544 基准测试段
            ("http://198.18.0.10", True, False),  # allow_local=True 也不放行
            ("http://192.0.2.1", False, False),  # TEST-NET-1
            ("http://198.51.100.1", False, False),  # TEST-NET-2
            ("http://203.0.113.1", False, False),  # TEST-NET-3
            # IANA 特例：is_private=False 但属保留用途（PCP anycast），须显式拦截
            ("http://192.0.0.9", False, False),
            ("http://192.0.0.10", False, False),
            # Dev 模式允许本地
            ("http://127.0.0.1:8000", True, True),
            ("http://localhost:8000", True, True),
        ],
    )
    def test_classification(self, url: str, allow_local: bool, expected: bool, public_dns) -> None:
        assert is_safe_http_url(url, allow_local=allow_local) is expected

    def test_assert_raises_unsafe(self) -> None:
        with pytest.raises(UnsafeURLError):
            assert_safe_http_url("http://127.0.0.1:8000")

    def test_non_standard_port_default_rejected(self, public_dns) -> None:
        """严格模式下非 80/443 端口拒绝。"""
        assert is_safe_http_url("https://api.example.com:8443", allow_local=False) is False
        assert is_safe_http_url("https://api.example.com:443", allow_local=False) is True

    def test_port_whitelist_override(self, public_dns) -> None:
        allowed = frozenset({80, 443, 8443})
        assert is_safe_http_url(
            "https://api.example.com:8443", allow_local=False, allowed_ports=allowed
        ) is True

    def test_ipv6_literal_loopback_rejected(self) -> None:
        """IPv6 字面量 [::1] 也走严格拒绝。"""
        assert is_safe_http_url("http://[::1]", allow_local=False) is False
        assert is_safe_http_url("http://[::ffff:127.0.0.1]", allow_local=False) is False


class TestPinSafeHttpUrl:
    def test_pin_literal_ip_loopback_dev(self) -> None:
        target = pin_safe_http_url("http://127.0.0.1:11434/v1", allow_local=True)
        assert target.hostname == "127.0.0.1"
        assert target.pinned_ip == "127.0.0.1"
        assert target.port == 11434

    def test_pin_rejects_unsafe(self) -> None:
        with pytest.raises(UnsafeURLError):
            pin_safe_http_url("http://127.0.0.1:11434/v1", allow_local=False)

    def test_pin_public_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ipaddress

        monkeypatch.setattr(
            "shared.core.security.url._resolve_all",
            lambda host: [ipaddress.ip_address("93.184.216.34")],
        )
        target = pin_safe_http_url("https://example.com/v1", allow_local=False)
        assert target.hostname == "example.com"
        assert target.pinned_ip == "93.184.216.34"


@pytest.mark.asyncio
async def test_pinned_host_transport_rewrites_to_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """出站请求 host 改为 pin IP，Host 头与 sni_hostname 保留原域名。"""
    captured: dict = {}

    class _Inner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured["host"] = request.url.host
            captured["header_host"] = request.headers.get("host")
            captured["sni"] = (request.extensions or {}).get("sni_hostname")
            return httpx.Response(200, json={"ok": True}, request=request)

    import shared.core.security.url as sec_url

    monkeypatch.setattr(
        sec_url.httpx,
        "AsyncHTTPTransport",
        lambda **kw: _Inner(),
    )
    transport = PinnedHostTransport(hostname="api.example.com", pinned_ip="1.2.3.4")
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("https://api.example.com/v1/models")
    assert resp.status_code == 200
    assert captured["host"] == "1.2.3.4"
    assert captured["header_host"] == "api.example.com"
    assert captured["sni"] == "api.example.com"