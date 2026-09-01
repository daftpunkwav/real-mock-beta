"""OpenAI Responses API 协议转换：input items 与工具 schema。

仅负责「内部 OpenAI 风格 → Responses API 请求体片段」的纯转换，
不涉及请求 URL / 响应解析（见 :mod:`protocol_translate` 与 :mod:`response_extract`）。
"""

from __future__ import annotations

from typing import Any

from .protocol_utils import _json_arguments


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


__all__ = [
    "_responses_input",
    "_responses_tools",
]
