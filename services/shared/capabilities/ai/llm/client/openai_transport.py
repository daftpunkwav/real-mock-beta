"""OpenAI Chat Completions 传输：请求执行、JSON 输出解析修复、embeddings 调用。

LLMClient 在 ``protocol == openai_chat`` 时使用本模块；SSRF 检查在调用前
完成（本模块不重复校验），重试统一走 ``base._retry_request``。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from shared.config import get_settings
from shared.core.security import (
    make_pinned_async_client,
    redact_api_key,
)
from shared.core.secrets import LegacySecretFormatError, decrypt_secret

from .base import _is_local_allowed, _require_https, _retry_request

logger = logging.getLogger(__name__)


def build_payload(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None,
    stream: bool = False,
    response_format: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens_override: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens_override if max_tokens_override is not None else max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if response_format:
        payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
    if reasoning_effort:
        payload["reasoning_effort"] = (
            "high" if reasoning_effort == "max" else reasoning_effort
        )
    return payload


def chat_completions_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def chat_completions(
    *,
    api_base: str,
    api_key: str,
    url: str,
    payload: dict[str, Any],
    timeout: float,
    log_label: str,
    model: str,
) -> dict[str, Any]:
    """POST Chat Completions 并返回 JSON；4xx/429/5xx 重试语义在 base。"""
    async with make_pinned_async_client(
        api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=timeout
    ) as client:
        try:
            resp = await _retry_request(
                lambda: client.post(url, headers=chat_completions_headers(api_key), json=payload)
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "%s 失败: model=%s status=%s key=%s",
                log_label,
                model,
                e.response.status_code,
                redact_api_key(api_key),
            )
            raise


def strip_code_fences(text: str) -> str:
    """剥掉 LLM 可能裹在 JSON 外的 Markdown 代码围栏。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def repair_common_json_errors(text: str) -> str:
    """修复 LLM 输出 JSON 的常见语法错误。

    - 剥掉对象/数组末尾的尾随逗号；
    - 字符串内部的裸控制字符（换行/制表符等 <0x20）转义为 \\n / \\t。
    字符串边界逐字符追踪，字符串外内容原样保留。
    """
    out: list[str] = []
    in_str = False
    escape = False
    n = len(text)
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_str = False
                out.append(ch)
                continue
            if ord(ch) < 0x20:
                out.append("\\n" if ch == "\n" else "\\t" if ch == "\t" else "\\r" if ch == "\r" else f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                continue  # 尾随逗号,丢弃
        out.append(ch)
    return "".join(out)


async def embed_texts(
    *,
    texts: list[str],
    model: str,
    api_base: str,
    api_key: str,
) -> list[list[float]]:
    """调用 OpenAI 兼容 /embeddings 端点，返回每段文本的向量。"""
    settings = get_settings()
    base = settings.effective_embeddings_base
    url = f"{base}/embeddings"
    payload: dict[str, Any] = {
        "model": model or settings.effective_embeddings_model,
        "input": texts,
    }
    raw_embed = settings.effective_embeddings_key
    try:
        embed_key = (decrypt_secret(raw_embed) if raw_embed else None)
        if not embed_key:
            embed_key = decrypt_secret(api_key) if api_key else ""
    except LegacySecretFormatError as e:
        logger.error("Embeddings API Key 使用旧版加密格式，请重新保存: %s", e)
        raise
    except ValueError as e:
        logger.error("Embeddings API Key 解密失败，已中止请求（不回退明文）: %s", e)
        raise
    headers = {
        "Authorization": f"Bearer {embed_key}",
        "Content-Type": "application/json",
    }
    async with make_pinned_async_client(
        base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=60.0
    ) as client:
        try:
            resp = await _retry_request(
                lambda: client.post(url, headers=headers, json=payload)
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "LLM embed 失败: model=%s status=%s key=%s",
                payload["model"],
                e.response.status_code,
                redact_api_key(embed_key),
            )
            raise

    return [item["embedding"] for item in data["data"]]


__all__ = [
    "build_payload",
    "chat_completions_headers",
    "chat_completions",
    "strip_code_fences",
    "repair_common_json_errors",
    "embed_texts",
]
