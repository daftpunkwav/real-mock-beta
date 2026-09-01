"""流式传输执行：SSE 解析、usage 采集、stream_options 降级信号。

统一客户端（unified_client）与 OpenAI 兼容客户端（llm_client）共用的
流式请求执行层；``stream_options`` 被端点显式拒绝时的降级路径在此收敛。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from shared.core.prompts import strip_emojis
from shared.core.security import make_pinned_async_client

from .assemblers import _AnthropicRoundAssembler, _OpenAIRoundAssembler
from .base import _is_local_allowed, _require_https
from .protocol_utils import _headers
from .response_extract import parse_sse_event
from ..stream_filters import StreamSanitizer

logger = logging.getLogger(__name__)


class _StreamOptionsUnsupported(Exception):
    """流式端点显式拒绝 ``stream_options``（请求体 400/422 且错误信息点名该字段）。"""


async def stream_message_round(
    client: Any,
    api_base: str,
    protocol: str,
    api_key: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """执行一次流式工具轮：reasoning 增量即时产出，结束时产出组装好的 message。

    供 ``chat_message_stream`` 使用；``stream_options`` 被端点拒绝时抛
    :class:`_StreamOptionsUnsupported`，由调用方去掉该字段后重放。
    """
    if protocol == "anthropic_messages":
        assembler: Any = _AnthropicRoundAssembler()
    else:
        assembler = _OpenAIRoundAssembler()
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        async with c.stream(
            "POST", url, headers=_headers(api_key, protocol), json=payload
        ) as resp:
            if "stream_options" in payload and resp.status_code in (400, 422):
                body = (await resp.aread()).decode("utf-8", "ignore")
                if "stream_options" in body:
                    raise _StreamOptionsUnsupported(body[:120])
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                client.usage.record_stream_event(event, protocol)
                reasoning = strip_emojis(assembler.feed(event))
                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}
    yield {"type": "message", "message": assembler.message()}


async def stream_text_payload(
    client: Any,
    api_base: str,
    protocol: str,
    api_key: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    """执行一次流式请求并产出净化后的文本增量（含 usage 采集）。

    供 ``chat_stream`` 使用；``stream_options`` 被端点拒绝时抛
    :class:`_StreamOptionsUnsupported`，由调用方去掉该字段后重放。
    """
    sanitizer = StreamSanitizer()
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        async with c.stream(
            "POST", url, headers=_headers(api_key, protocol), json=payload
        ) as resp:
            if "stream_options" in payload and resp.status_code in (400, 422):
                body = (await resp.aread()).decode("utf-8", "ignore")
                if "stream_options" in body:
                    raise _StreamOptionsUnsupported(body[:120])
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                client.usage.record_stream_event(event, protocol)
                token, reasoning = parse_sse_event(event, protocol)
                if reasoning:
                    cleaned = sanitizer.feed_reasoning(reasoning)
                    if cleaned:
                        yield cleaned
                if token:
                    cleaned = sanitizer.feed_content(token)
                    if cleaned:
                        yield cleaned
            tail = sanitizer.flush()
            if tail:
                yield tail


__all__ = ["_StreamOptionsUnsupported", "stream_message_round", "stream_text_payload"]
