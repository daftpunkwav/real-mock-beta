"""LLMClient 的 OpenAI 兼容流式执行：重试 + stream_options 降级。

``chat_message_stream``（工具轮）与 ``chat_stream``（文本增量）共用：
- 4xx 不重试（stream_options 被点名拒绝时去掉该字段重放）；
- 429/5xx / 连接类错误在未产出增量前指数退避重试（默认 3 次）；
- 已产出增量后失败直接抛（重试无法补救半截流）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from shared.core.security import make_pinned_async_client

from .assemblers import _OpenAIRoundAssembler
from .base import _is_local_allowed, _require_https
from .openai_transport import chat_completions_headers
from ..stream_filters import StreamSanitizer

logger = logging.getLogger(__name__)

_RETRYABLE_CONNECTION_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)


async def stream_message_round_retry(
    client: Any,
    api_base: str,
    api_key: str,
    model: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """流式一轮工具循环（OpenAI Chat 兼容）：reasoning 增量即时产出，末尾组装 message。

    429/5xx/连接错误在未产出增量前指数退避重试；``stream_options`` 被端点
    拒绝时置位 ``_stream_usage_disabled`` 后去掉该字段重放。
    """
    headers = chat_completions_headers(api_key)
    max_retries = 3
    backoff = 0.5
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
    ) as c:
        for attempt in range(max_retries + 1):
            assembler = _OpenAIRoundAssembler()
            emitted = False
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code in (400, 422) and "stream_options" in payload:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "stream_options" in body:
                            client._stream_usage_disabled = True
                            logger.info(
                                "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s",
                                model,
                            )
                            payload.pop("stream_options", None)
                            if attempt < max_retries:
                                continue
                    # 先判 429/5xx 重试，再统一 raise_for_status——4xx 不重试、
                    # 429/5xx 在重试耗尽时才抛出（与 base._retry_request 语义一致）
                    if resp.status_code == 429 or resp.status_code >= 500:
                        if attempt < max_retries:
                            await asyncio.sleep(backoff * (2**attempt))
                            continue
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        client.usage.record_stream_event(chunk, client.protocol)
                        reasoning = assembler.feed(chunk)
                        if reasoning:
                            emitted = True
                            yield {"type": "reasoning", "text": reasoning}
                    yield {"type": "message", "message": assembler.message()}
                    return
            except _RETRYABLE_CONNECTION_ERRORS:
                if emitted or attempt >= max_retries:
                    raise
                await asyncio.sleep(backoff * (2**attempt))


async def stream_text_retry(
    client: Any,
    api_base: str,
    api_key: str,
    model: str,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    """流式返回净化后的文本 token（OpenAI Chat 兼容）。

    429/5xx/连接错误在未产出 token 前指数退避重试；sanitizer 按 attempt
    重建，失败重试时丢弃上次残留的半截特殊 token 缓冲与 <think> 开合状态。
    """
    headers = chat_completions_headers(api_key)
    max_retries = 3
    backoff = 0.5
    last_exc: Exception | None = None
    tokens_yielded = False
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=120.0
    ) as c:
        for attempt in range(max_retries + 1):
            # sanitizer 按 attempt 重建:失败重试时丢弃上次残留的
            # 半截特殊 token 缓冲与 <think> 开合状态,避免污染新流
            sanitizer = StreamSanitizer()
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code in (400, 422) and "stream_options" in payload:
                        # 供应商不支持 stream_options：可见降级（记日志）后去掉重试
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "stream_options" in body:
                            client._stream_usage_disabled = True
                            logger.info(
                                "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s",
                                model,
                            )
                            payload.pop("stream_options", None)
                            if attempt < max_retries:
                                continue
                    # 先判 429/5xx 重试，再统一 raise_for_status（同 stream_message_round_retry）
                    if resp.status_code == 429 or resp.status_code >= 500:
                        last_exc = httpx.HTTPStatusError(
                            f"transient {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(backoff * (2**attempt))
                            continue
                        raise last_exc
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            client.usage.record_stream_event(chunk, client.protocol)
                            delta = chunk["choices"][0].get("delta", {})
                            if not isinstance(delta, dict):
                                continue
                            reasoning = (
                                delta.get("reasoning_content")
                                or delta.get("reasoning")
                                or ""
                            )
                            token = delta.get("content") or ""
                            if isinstance(reasoning, str) and reasoning:
                                cleaned_r = sanitizer.feed_reasoning(reasoning)
                                if cleaned_r:
                                    tokens_yielded = True
                                    yield cleaned_r
                            if isinstance(token, str) and token:
                                cleaned = sanitizer.feed_content(token)
                                if cleaned:
                                    tokens_yielded = True
                                    yield cleaned
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                    tail = sanitizer.flush()
                    if tail:
                        tokens_yielded = True
                        yield tail
                    return
            except _RETRYABLE_CONNECTION_ERRORS as e:
                if tokens_yielded:
                    raise
                last_exc = e
                if attempt < max_retries:
                    await asyncio.sleep(backoff * (2**attempt))
                    continue
                raise
        if last_exc is not None:
            raise last_exc


__all__ = ["stream_message_round_retry", "stream_text_retry"]
