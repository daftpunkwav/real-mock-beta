"""Mimo / OpenAI 兼容统一客户端：支持 chat completions / anthropic messages / responses。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_PROTOCOL, LLMProtocol
from shared.core.prompts import strip_emojis
from shared.core.security import UnsafeURLError, is_safe_http_url, make_pinned_async_client, redact_api_key
from shared.core.secrets import LegacySecretFormatError, decrypt_secret
from shared.capabilities.ai.llm.stream_filters import StreamSanitizer
from shared.capabilities.ai.llm.usage import UsageAccumulator

from .base import _is_local_allowed, _require_https

logger = logging.getLogger(__name__)

# 思考强度 → Anthropic extended thinking 预算（tokens）
_ANTHROPIC_THINKING_BUDGET = {
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "max": 32768,
}


class _StreamOptionsUnsupported(Exception):
    """流式端点显式拒绝 ``stream_options``（请求体 400/422 且错误信息点名该字段）。"""


class _OpenAIRoundAssembler:
    """openai_chat 流式增量 → (reasoning 增量, 组装完整 message)。

    reasoning 即时回传；正文与 tool_calls（id/name/arguments 分片按 index
    拼接）缓冲到流结束，组装出与非流式 ``chat_message`` 同构的 message。
    """

    def __init__(self) -> None:
        self._content: list[str] = []
        self._calls: dict[int, dict[str, Any]] = {}

    def feed(self, event: dict[str, Any]) -> str:
        choices = event.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        if not isinstance(delta, dict):
            return ""
        reasoning = ""
        rc = delta.get("reasoning_content") or delta.get("reasoning") or ""
        if isinstance(rc, str) and rc:
            reasoning = rc
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._content.append(content)
        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            idx = int(tc.get("index") or 0)
            slot = self._calls.setdefault(
                idx, {"id": "", "function": {"name": "", "arguments": ""}}
            )
            if tc.get("id"):
                slot["id"] = str(tc["id"])
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] += str(fn["name"])
            if fn.get("arguments"):
                slot["function"]["arguments"] += str(fn["arguments"])
        return reasoning

    def message(self) -> dict[str, Any]:
        tool_calls = [
            {
                "id": self._calls[idx]["id"] or f"call_{idx}",
                "type": "function",
                "function": self._calls[idx]["function"],
            }
            for idx in sorted(self._calls)
        ]
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._content) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


class _AnthropicRoundAssembler:
    """anthropic_messages 流事件 → (reasoning 增量, 组装完整 message)。

    thinking_delta 即时回传；text_delta 与 tool_use（input_json_delta 分片
    拼接）缓冲到流结束组装。签名块（signature_delta）不透出。
    """

    def __init__(self) -> None:
        self._text: list[str] = []
        self._blocks: dict[int, dict[str, str]] = {}

    def feed(self, event: dict[str, Any]) -> str:
        etype = event.get("type")
        if etype == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                idx = int(event.get("index") or 0)
                self._blocks[idx] = {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "args": "",
                }
            return ""
        if etype != "content_block_delta":
            return ""
        idx = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        dtype = delta.get("type")
        if dtype == "thinking_delta":
            return str(delta.get("thinking") or "")
        if dtype == "text_delta":
            self._text.append(str(delta.get("text") or ""))
        elif dtype == "input_json_delta":
            if idx in self._blocks:
                self._blocks[idx]["args"] += str(delta.get("partial_json") or "")
        return ""

    def message(self) -> dict[str, Any]:
        tool_calls = [
            {
                "id": self._blocks[idx]["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": self._blocks[idx]["name"],
                    "arguments": self._blocks[idx]["args"] or "{}",
                },
            }
            for idx in sorted(self._blocks)
        ]
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._text) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


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
        reasoning_effort: str | None = None,
        usage_sink: UsageAccumulator | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.protocol = protocol
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort or None
        # 用量累计：缺省自建（独立使用），由 LLMClient 委派时共享同一 sink
        self.usage = usage_sink if usage_sink is not None else UsageAccumulator()
        self._stream_usage_disabled = False

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
            if self.reasoning_effort:
                # 思考强度 → extended thinking 预算；预算不得超过 max_tokens
                budget = _ANTHROPIC_THINKING_BUDGET.get(self.reasoning_effort, 8192)
                payload["max_tokens"] = max(self.max_tokens, budget + 1024)
                payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
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
            if self.reasoning_effort:
                payload["reasoning"] = {"effort": "high" if self.reasoning_effort == "max" else self.reasoning_effort}
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
        if self.reasoning_effort:
            payload["reasoning_effort"] = "high" if self.reasoning_effort == "max" else self.reasoning_effort
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

    @staticmethod
    def _extract_reasoning(data: dict[str, Any], protocol: str) -> str:
        """提取思考过程文本（无则空串）。

        - anthropic_messages：content 里的 ``thinking`` 块拼接；
        - openai_chat：message 的 ``reasoning_content`` / ``reasoning``；
        - openai_responses：reasoning item 只含摘要且多数网关不回传，不提取。
        """
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            content = data.get("content", [])
            if isinstance(content, list):
                return "".join(
                    str(item.get("thinking") or "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "thinking"
                )
            return ""
        msg = (data.get("choices") or [{}])[0].get("message", {}) if data.get("choices") else {}
        for key in ("reasoning_content", "reasoning"):
            val = msg.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return ""

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
        self.usage.record_response(data, self.protocol)
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
        self.usage.record_response(data, self.protocol)
        result: dict[str, Any] = {
            "role": "assistant",
            "content": self._extract_text(data, self.protocol),
            "tool_calls": self._extract_tool_calls(data, self.protocol),
        }
        # 思考过程仅随 message 回传供展示，不写入消息序列
        reasoning = self._extract_reasoning(data, self.protocol)
        if reasoning.strip():
            result["reasoning"] = strip_emojis(reasoning)
        return result

    async def chat_message_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式执行一轮工具循环调用：思考增量实时产出，正文/工具调用缓冲组装。

        产出 ``{"type": "reasoning", "text": ...}`` 增量事件，最后产出
        ``{"type": "message", "message": {...}}``（与非流式 ``chat_message``
        同构；reasoning 已实时下发，不再重复携带）。openai_responses 协议
        不支持时抛 :class:`NotImplementedError`，调用方回落非流式。
        """
        if self.protocol == LLMProtocol.OPENAI_RESPONSES:
            raise NotImplementedError("responses 协议不支持流式工具轮")
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages, system=system, stream=True, temperature=temperature, tools=tools
        )
        if self.protocol == LLMProtocol.OPENAI_CHAT and not self._stream_usage_disabled:
            payload["stream_options"] = {"include_usage": True}
        try:
            async for event in self._stream_round_events(url, payload):
                yield event
            return
        except _StreamOptionsUnsupported:
            self._stream_usage_disabled = True
            logger.info(
                "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s", self.model
            )
            payload.pop("stream_options", None)
            async for event in self._stream_round_events(url, payload):
                yield event

    async def _stream_round_events(
        self, url: str, payload: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """执行一次流式请求：reasoning 增量即时产出，结束时产出组装好的 message。"""
        if self.protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            assembler: Any = _AnthropicRoundAssembler()
        else:
            assembler = _OpenAIRoundAssembler()
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            async with client.stream(
                "POST", url, headers=_headers(self.api_key, self.protocol), json=payload
            ) as resp:
                if resp.status_code in (400, 422) and "stream_options" in payload:
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
                    self.usage.record_stream_event(event, self.protocol)
                    reasoning = strip_emojis(assembler.feed(event))
                    if reasoning:
                        yield {"type": "reasoning", "text": reasoning}
        yield {"type": "message", "message": assembler.message()}

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """解析三种协议的 SSE 文本增量。

        reasoning 增量（Anthropic ``thinking_delta`` / OpenAI ``reasoning_content``）
        统一包裹为 ``<think>...</think>``；正文经 ``StreamSanitizer`` 剥离模板 token。
        """
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages,
            system=system,
            stream=True,
            temperature=temperature,
            tools=tools,
        )
        if self.protocol == LLMProtocol.OPENAI_CHAT and not self._stream_usage_disabled:
            # 请求供应商回传 usage（最后一个 chunk）；被拒时按响应降级
            payload["stream_options"] = {"include_usage": True}
        try:
            async for piece in self._stream_payload(url, payload):
                yield piece
        except _StreamOptionsUnsupported:
            self._stream_usage_disabled = True
            logger.info(
                "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s", self.model
            )
            payload.pop("stream_options", None)
            async for piece in self._stream_payload(url, payload):
                yield piece

    async def _stream_payload(
        self, url: str, payload: dict[str, Any]
    ) -> AsyncIterator[str]:
        """执行一次流式请求并产出净化后的文本增量（含 usage 采集）。"""
        sanitizer = StreamSanitizer()
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            async with client.stream(
                "POST", url, headers=_headers(self.api_key, self.protocol), json=payload
            ) as resp:
                if resp.status_code in (400, 422) and "stream_options" in payload:
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
                    self.usage.record_stream_event(event, self.protocol)
                    token = ""
                    reasoning = ""
                    if self.protocol == LLMProtocol.ANTHROPIC_MESSAGES:
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta") or {}
                            if delta.get("type") == "thinking_delta":
                                reasoning = str(delta.get("thinking") or "")
                            else:
                                token = str(delta.get("text") or "")
                    elif self.protocol == LLMProtocol.OPENAI_RESPONSES:
                        if event.get("type") == "response.output_text.delta":
                            token = str(event.get("delta") or "")
                    else:
                        choices = event.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            if not isinstance(delta, dict):
                                continue
                            token = str(delta.get("content") or "")
                            reasoning = str(
                                delta.get("reasoning_content") or delta.get("reasoning") or ""
                            )
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
