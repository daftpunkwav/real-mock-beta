"""LLM 协议转译：三协议请求体构建、消息/工具转换、响应与 SSE 事件解析。

openai_chat / anthropic_messages / openai_responses 三种 API 的差异全部
收敛在本模块（含思考强度 → 各协议参数的映射），客户端主类只做分发。
"""

from __future__ import annotations

import json
from typing import Any

from shared.core.constants import LLMProtocol

# 思考强度 → Anthropic extended thinking 预算（tokens）
_ANTHROPIC_THINKING_BUDGET = {
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "max": 32768,
}


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


def build_request(
    protocol: str,
    api_base: str,
    model: str,
    max_tokens: int,
    reasoning_effort: str | None,
    messages: list[dict[str, Any]],
    system: str | None = None,
    stream: bool = False,
    temperature: float = 0.7,
    response_format: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """按协议构建请求 URL 与 payload（三种形状各自保持，不互相统一）。"""
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        message_items = _anthropic_messages(messages)
        system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
        system_text = system or "\n".join(part for part in system_parts if part)
        url = f"{api_base}/v1/messages"
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
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
        if reasoning_effort:
            # 思考强度 → extended thinking 预算；预算不得超过 max_tokens
            budget = _ANTHROPIC_THINKING_BUDGET.get(reasoning_effort, 8192)
            payload["max_tokens"] = max(max_tokens, budget + 1024)
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return url, payload

    if protocol == LLMProtocol.OPENAI_RESPONSES:
        message_items = _responses_input(messages)
        system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
        system_text = system or "\n".join(part for part in system_parts if part)
        url = f"{api_base}/responses"
        payload = {
            "model": model,
            "input": message_items,
            "max_output_tokens": max_tokens,
            "stream": stream,
        }
        if system_text:
            payload["instructions"] = system_text
        if response_format:
            payload["text"] = {"format": response_format}
        if reasoning_effort:
            payload["reasoning"] = {"effort": "high" if reasoning_effort == "max" else reasoning_effort}
        responses_tools = _responses_tools(tools)
        if responses_tools:
            payload["tools"] = responses_tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return url, payload

    # 默认 openai_chat
    url = f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if response_format:
        payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if reasoning_effort:
        payload["reasoning_effort"] = "high" if reasoning_effort == "max" else reasoning_effort
    return url, payload


def extract_text(data: dict[str, Any], protocol: str) -> str:
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


def extract_tool_calls(data: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
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


def extract_reasoning(data: dict[str, Any], protocol: str) -> str:
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


def parse_sse_event(event: dict[str, Any], protocol: str) -> tuple[str, str]:
    """从单个 SSE 事件提取 (正文增量, 思考增量)；不识别的事件返回 ("", "")。"""
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "thinking_delta":
                return "", str(delta.get("thinking") or "")
            return str(delta.get("text") or ""), ""
        return "", ""
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        if event.get("type") == "response.output_text.delta":
            return str(event.get("delta") or ""), ""
        return "", ""
    # openai_chat
    choices = event.get("choices") or []
    if not choices:
        return "", ""
    delta = choices[0].get("delta") or {}
    if not isinstance(delta, dict):
        return "", ""
    token = str(delta.get("content") or "")
    reasoning = str(delta.get("reasoning_content") or delta.get("reasoning") or "")
    return token, reasoning


__all__ = [
    "_ANTHROPIC_THINKING_BUDGET",
    "_headers",
    "_json_arguments",
    "_anthropic_messages",
    "_responses_input",
    "_anthropic_tools",
    "_responses_tools",
    "_anthropic_tool_choice",
    "build_request",
    "extract_text",
    "extract_tool_calls",
    "extract_reasoning",
    "parse_sse_event",
]
