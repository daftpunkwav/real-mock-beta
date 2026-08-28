"""应用层安全辅助。

保持向后兼容的 import 路径：``from shared.core.security import ...``

拆分后的子模块：

- :mod:`file` — 文件名清洗、路径穿越防御
- :mod:`url` — URL/SSRF 过滤、DNS pin、安全 HTTP 客户端
- :mod:`redact` — API Key 脱敏
"""

from .file import assert_within_dir, sanitize_filename
from .redact import redact_api_key
from .url import (
    MIMO_TRUSTED_HOSTS,
    PinnedHostTransport,
    PinnedHttpTarget,
    UnsafeURLError,
    assert_safe_http_url,
    is_localhost_family,
    is_safe_http_url,
    make_pinned_async_client,
    pin_safe_http_url,
)

__all__ = [
    "MIMO_TRUSTED_HOSTS",
    "PinnedHostTransport",
    "PinnedHttpTarget",
    "UnsafeURLError",
    "assert_safe_http_url",
    "assert_within_dir",
    "is_localhost_family",
    "is_safe_http_url",
    "make_pinned_async_client",
    "pin_safe_http_url",
    "redact_api_key",
    "sanitize_filename",
]
