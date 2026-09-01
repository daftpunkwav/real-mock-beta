"""LLM 响应解析：正文 / 工具调用 / 思考过程提取，与 SSE 事件增量解析。

纯函数输入（response JSON 或单个 SSE 事件）+ 协议，输出统一形状；
不发起网络请求（见 :mod:`streaming`）。
"""

from __future__ import annotations

from typing import Any

from shared.core.constants import LLMProtocol

from .protocol_utils import _json_arguments


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
    "extract_text",
    "extract_tool_calls",
    "extract_reasoning",
    "parse_sse_event",
]
