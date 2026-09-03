"""LLM 客户端公共基础：重试、文本提取、环境检查。

从原 ``client.py`` 和 ``unified_client.py`` 中提取的共享辅助函数。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from shared.config import get_settings
from shared.core.prompts import strip_emojis

logger = logging.getLogger(__name__)


def _extract_message_text(msg: dict[str, Any] | None) -> str:
    """从 Chat Completions message 中提取可读文本。

    兼容：
    - 标准 ``content`` 字符串
    - 部分厂商把正文放在 ``reasoning_content`` / ``reasoning``
    - content 为 list（多段 text）

    出站前剥离 emoji，避免模型无视 system 约束。
    """
    if not msg or not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return strip_emojis(content)
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        joined = "".join(parts).strip()
        if joined:
            return strip_emojis(joined)
    for key in ("reasoning_content", "reasoning", "output_text"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return strip_emojis(val)
    if isinstance(content, str):
        return strip_emojis(content)
    return ""


async def _retry_request(
    coro_factory,
    *,
    max_retries: int = 3,
    backoff: float = 0.5,
    is_stream: bool = False,
) -> httpx.Response:
    """对 429/5xx 指数退避重试；4xx 直接抛出。

    ``coro_factory`` 是无参 callable，每次返回新的 coroutine（避免同一
    response 被多次 await）。``is_stream=True`` 时调用方自行处理流关闭。
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        coro = coro_factory()
        try:
            resp = await coro
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else 0
            if status_code == 429 or status_code >= 500:
                last_exc = e
                if attempt < max_retries:
                    if is_stream:
                        try:
                            await e.response.aclose()
                        except Exception:
                            pass
                    await asyncio.sleep(backoff * (2 ** attempt))
                    continue
            raise
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < max_retries:
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            raise
        if resp.status_code == 429 or resp.status_code >= 500:
            last_exc = httpx.HTTPStatusError(
                f"transient {resp.status_code}",
                request=resp.request,
                response=resp,
            )
            if attempt < max_retries:
                if is_stream:
                    try:
                        await resp.aclose()
                    except Exception:
                        pass
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            resp.raise_for_status()
        return resp
    assert last_exc is not None
    raise last_exc


def _is_local_allowed() -> bool:
    """每次请求重新计算，避免模块级缓存的环境变量无法响应测试 monkeypatch。"""
    return bool(get_settings().allow_local_llm)


def _require_https() -> bool:
    """生产环境出站强制 HTTPS。"""
    return bool(get_settings().is_prod)
