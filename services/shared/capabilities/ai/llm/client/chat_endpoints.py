"""UnifiedLLMClient 非流式端点：``chat`` / ``test_connection`` / ``chat_message``。

三者共享「构建 URL+payload → pinned client POST → 解析响应」的同步请求路径，
从 ``unified_client`` 主文件拆出；SSRF 检查与出站 pinned client 语义不变。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from shared.core.prompts import strip_emojis
from shared.core.security import (
    make_pinned_async_client,
    redact_api_key,
)

from .base import _is_local_allowed, _require_https
from .protocol_utils import _headers
from .response_extract import extract_reasoning, extract_text, extract_tool_calls

if TYPE_CHECKING:
    from .unified_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


async def chat(
    client: "UnifiedLLMClient",
    messages: list[dict[str, Any]],
    system: str | None = None,
    temperature: float = 0.7,
    response_format: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    client._safe_check()
    url, payload = client._build_url_and_payload(
        messages, system=system, stream=False, temperature=temperature, response_format=response_format, tools=tools
    )
    async with make_pinned_async_client(
        client.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as http:
        try:
            resp = await http.post(
                url, headers=_headers(client.api_key, client.protocol), json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Unified LLM chat 失败: model=%s status=%s key=%s",
                client.model,
                e.response.status_code,
                redact_api_key(client.api_key),
            )
            raise
    client.usage.record_response(data, client.protocol)
    return extract_text(data, client.protocol)


async def test_connection(client: "UnifiedLLMClient") -> tuple[bool, str]:
    client._safe_check()
    url, payload = client._build_url_and_payload(
        [{"role": "user", "content": "请回复：连接成功"}],
        system="只用纯文字回复，禁止任何 emoji 表情符号。",
        stream=False,
        temperature=0,
    )
    async with make_pinned_async_client(
        client.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=60.0
    ) as http:
        try:
            resp = await http.post(
                url, headers=_headers(client.api_key, client.protocol), json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            text = extract_text(data, client.protocol)
            return True, text[:100]
        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            return False, str(e)


async def chat_message(
    client: "UnifiedLLMClient",
    messages: list[dict[str, Any]],
    system: str | None = None,
    temperature: float = 0.7,
    response_format: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """返回文本和统一后的 function tool calls。"""
    client._safe_check()
    url, payload = client._build_url_and_payload(
        messages,
        system=system,
        stream=False,
        temperature=temperature,
        response_format=response_format,
        tools=tools,
        tool_choice=tool_choice,
    )
    async with make_pinned_async_client(
        client.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as http:
        resp = await http.post(
            url, headers=_headers(client.api_key, client.protocol), json=payload
        )
        resp.raise_for_status()
        data = resp.json()
    client.usage.record_response(data, client.protocol)
    result: dict[str, Any] = {
        "role": "assistant",
        "content": extract_text(data, client.protocol),
        "tool_calls": extract_tool_calls(data, client.protocol),
    }
    # 思考过程仅随 message 回传供展示，不写入消息序列
    reasoning = extract_reasoning(data, client.protocol)
    if reasoning.strip():
        result["reasoning"] = strip_emojis(reasoning)
    return result


__all__ = ["chat", "chat_message", "test_connection"]
