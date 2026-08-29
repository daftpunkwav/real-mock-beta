"""Mimo / OpenAI 兼容统一客户端：支持 chat completions / anthropic messages / responses。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_PROTOCOL, LLMProtocol
from shared.core.security import UnsafeURLError, is_safe_http_url, make_pinned_async_client, redact_api_key
from shared.core.secrets import LegacySecretFormatError, decrypt_secret

from .base import _is_local_allowed, _require_https

logger = logging.getLogger(__name__)


def _headers(api_key: str, protocol: str) -> dict[str, str]:
    headers = {
        "api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    return headers


def _json_arguments(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except TypeError:
        return "{}"


def _anthropic_content_blocks(content: Any) -> Any:
    """把 OpenAI 风格的数组 content 转为 Anthropic content blocks。

    内部消息采用 OpenAI 风格 ``image_url`` 图像块；Anthropic Messages API
    只接受 ``text`` / ``image`` blocks，原样透传会被网关拒绝
    （400 unsupported content type 'image_url'），此处统一转换。
    """
    if not isinstance(content, list):
        return content or ""
    blocks: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            blocks.append({"type": "text", "text": str(part)})
            continue
        ptype = part.get("type")
        if ptype == "image_url":
            url = ((part.get("image_url") or {}).get("url")) or ""
            if url.startswith("data:"):
                header, _, data = url.partition(",")
                media_type = header[5:].split(";", 1)[0] or "image/jpeg"
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
            elif url:
                blocks.append({"type": "image", "source": {"type": "url", "url": url}})
            continue
        if ptype == "text":
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        blocks.append(part)
    return blocks


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将内部 OpenAI 风格消息转换为 Anthropic content blocks。"""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id") or "",
                            "content": str(message.get("content") or ""),
                        }
                    ],
                }
            )
            continue
        tool_calls = message.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            blocks: list[dict[str, Any]] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": str(message["content"])})
            for call in tool_calls:
                function = call.get("function") or {}
                arguments = function.get("arguments") or {}
                try:
                    arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    arguments = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": function.get("name") or "",
                        "input": arguments,
                    }
                )
            converted.append({"role": "assistant", "content": blocks})
            continue
        converted.append({
            "role": role or "user",
            "content": _anthropic_content_blocks(message.get("content")),
        })
    return converted


def _responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将内部工具消息转换为 Responses API input items。"""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            converted.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id") or "",
                    "output": str(message.get("content") or ""),
                }
            )
            continue
        tool_calls = message.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            if message.get("content"):
                converted.append(
                    {"role": "assistant", "content": str(message["content"])}
                )
            for call in tool_calls:
                function = call.get("function") or {}
                converted.append(
                    {
                        "type": "function_call",
                        "call_id": call.get("id") or "",
                        "name": function.get("name") or "",
                        "arguments": _json_arguments(function.get("arguments")),
                    }
                )
            continue
        converted.append({"role": role or "user", "content": message.get("content") or ""})
    return converted


def _anthropic_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(function, dict):
            continue
        converted.append(
            {
                "name": function.get("name") or "",
                "description": function.get("description") or "",
                "input_schema": function.get("parameters") or {"type": "object"},
            }
        )
    return converted


def _responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(function, dict):
            continue
        converted.append(
            {
                "type": "function",
                "name": function.get("name") or "",
                "description": function.get("description") or "",
                "parameters": function.get("parameters") or {"type": "object"},
            }
        )
    return converted


def _anthropic_tool_choice(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        return {"type": value}
    if value.get("type") == "function":
        function = value.get("function") or {}
        return {"type": "tool", "name": function.get("name") or ""}
    return value


class UnifiedLLMClient:
    """根据 protocol 字段选择正确的 API 路径和 payload 格式。"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        protocol: str = DEFAULT_LLM_PROTOCOL,
        max_tokens: int = 4096,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.protocol = protocol
        self.max_tokens = max_tokens

    @classmethod
    def from_stage_config(cls, config: dict[str, Any]) -> "UnifiedLLMClient":
        api_key = config.get("api_key") or ""
        if api_key.startswith("enc:"):
            try:
                api_key = decrypt_secret(api_key) or ""
            except LegacySecretFormatError as e:
                logger.error("API Key 使用旧版加密格式，请重新保存: %s", e)
                api_key = ""
            except ValueError as e:
                logger.error("API Key 解密失败: %s", e)
                api_key = ""
        return cls(
            api_base=config.get("api_base") or "",
            api_key=api_key,
            model=config.get("model") or "",
            protocol=config.get("protocol") or DEFAULT_LLM_PROTOCOL,
            max_tokens=config.get("max_tokens") or 4096,
        )

    def _safe_check(self) -> None:
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")

    def _build_url_and_payload(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if self.protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            message_items = _anthropic_messages(messages)
            system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
            system_text = system or "\n".join(part for part in system_parts if part)
            url = f"{self.api_base}/v1/messages"
            payload: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": message_items,
                "stream": stream,
            }
            if system_text:
                payload["system"] = system_text
            anthropic_tools = _anthropic_tools(tools)
            if anthropic_tools:
                payload["tools"] = anthropic_tools
            if tool_choice is not None:
                payload["tool_choice"] = _anthropic_tool_choice(tool_choice)
            return url, payload

        if self.protocol == LLMProtocol.OPENAI_RESPONSES:
            message_items = _responses_input(messages)
            system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
            system_text = system or "\n".join(part for part in system_parts if part)
            url = f"{self.api_base}/responses"
            payload = {
                "model": self.model,
                "input": message_items,
                "max_output_tokens": self.max_tokens,
                "stream": stream,
            }
            if system_text:
                payload["instructions"] = system_text
            if response_format:
                payload["text"] = {"format": response_format}
            responses_tools = _responses_tools(tools)
            if responses_tools:
                payload["tools"] = responses_tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
            return url, payload

        # 默认 openai_chat
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return url, payload

    @staticmethod
    def _extract_text(data: dict[str, Any], protocol: str) -> str:
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            content = data.get("content", [])
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    str(item.get("text") or "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            return ""
        if protocol == LLMProtocol.OPENAI_RESPONSES:
            if isinstance(data.get("output_text"), str):
                return data["output_text"]
            for item in data.get("output", []) or []:
                if isinstance(item, dict) and item.get("type") == "message":
                    content = item.get("content", [])
                    if isinstance(content, list):
                        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
                    return str(content or "")
            return ""

        msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        for key in ("output_text", "reasoning_content", "reasoning"):
            val = msg.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return ""

    @staticmethod
    def _extract_tool_calls(data: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            for item in data.get("content", []) or []:
                if not isinstance(item, dict) or item.get("type") != "tool_use":
                    continue
                calls.append(
                    {
                        "id": item.get("id") or "",
                        "type": "function",
                        "function": {
                            "name": item.get("name") or "",
                            "arguments": _json_arguments(item.get("input")),
                        },
                    }
                )
            return calls
        if protocol == LLMProtocol.OPENAI_RESPONSES:
            for item in data.get("output", []) or []:
                if not isinstance(item, dict) or item.get("type") != "function_call":
                    continue
                calls.append(
                    {
                        "id": item.get("call_id") or item.get("id") or "",
                        "type": "function",
                        "function": {
                            "name": item.get("name") or "",
                            "arguments": _json_arguments(item.get("arguments")),
                        },
                    }
                )
            return calls
        choices = data.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("tool_calls") or []
        return calls

    async def chat(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages, system=system, stream=False, temperature=temperature, response_format=response_format, tools=tools
        )
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            try:
                resp = await client.post(
                    url, headers=_headers(self.api_key, self.protocol), json=payload
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Unified LLM chat 失败: model=%s status=%s key=%s",
                    self.model,
                    e.response.status_code,
                    redact_api_key(self.api_key),
                )
                raise
        return self._extract_text(data, self.protocol)

    async def test_connection(self) -> tuple[bool, str]:
        self._safe_check()
        url, payload = self._build_url_and_payload(
            [{"role": "user", "content": "请回复：连接成功"}],
            system="只用纯文字回复，禁止任何 emoji 表情符号。",
            stream=False,
            temperature=0,
        )
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=60.0
        ) as client:
            try:
                resp = await client.post(
                    url, headers=_headers(self.api_key, self.protocol), json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                text = self._extract_text(data, self.protocol)
                return True, text[:100]
            except httpx.HTTPStatusError as e:
                return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            except Exception as e:
                return False, str(e)

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回文本和统一后的 function tool calls。"""
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages,
            system=system,
            stream=False,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
        )
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            resp = await client.post(
                url, headers=_headers(self.api_key, self.protocol), json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "role": "assistant",
            "content": self._extract_text(data, self.protocol),
            "tool_calls": self._extract_tool_calls(data, self.protocol),
        }

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """解析三种协议的 SSE 文本增量。"""
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages,
            system=system,
            stream=True,
            temperature=temperature,
            tools=tools,
        )
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            async with client.stream(
                "POST", url, headers=_headers(self.api_key, self.protocol), json=payload
            ) as resp:
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
                    token = ""
                    if self.protocol == LLMProtocol.ANTHROPIC_MESSAGES:
                        delta = event.get("delta") or {}
                        if event.get("type") == "content_block_delta":
                            token = str(delta.get("text") or "")
                    elif self.protocol == LLMProtocol.OPENAI_RESPONSES:
                        if event.get("type") == "response.output_text.delta":
                            token = str(event.get("delta") or "")
                    else:
                        choices = event.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            token = str(delta.get("content") or "")
                    if token:
                        yield token
