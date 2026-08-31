"""GitHub REST 调用的 HTTP 层：常量与错误形态映射。

拆自 :mod:`...github.client`；``GitHubClient._get`` 薄委托到 :func:`async_get`。
``httpx`` 为单例模块，测试 patch ``client.httpx.AsyncClient`` 在本模块同样命中。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0
# 单次响应 body 上限，防止 README/文件过大撑爆 context
MAX_TEXT_CHARS = 12_000


async def async_get(
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET ``path`` 并映射错误形态（404/403/>=400/空 body/JSON 失败）。"""
    url = f"{GITHUB_API}{path}"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(url, headers=headers or {}, params=params or {})
        if resp.status_code == 404:
            return {"error": "not_found", "path": path, "status": 404}
        if resp.status_code == 403:
            return {
                "error": "forbidden_or_rate_limited",
                "status": 403,
                "message": resp.text[:300],
            }
        if resp.status_code >= 400:
            return {
                "error": "http_error",
                "status": resp.status_code,
                "message": resp.text[:300],
            }
        # 空 body
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            text = resp.text
            return {"raw": text[:MAX_TEXT_CHARS]}
