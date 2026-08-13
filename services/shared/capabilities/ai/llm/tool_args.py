"""LLM function-calling 工具参数解析（共享，不属任何业务域）。

OpenAI / Anthropic / 自定义 OpenAI 协议：tool call arguments 通常是 JSON 字符串，
也可能是 dict（部分 SDK 提前解析）。此处统一处理。
"""

from __future__ import annotations

import json
from typing import Any


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """解析 LLM 返回的 tool arguments（可能是 JSON 字符串）。

    始终返回 dict；无法解析时返回 {}，由工具执行层处理缺参。
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


__all__ = ["parse_tool_arguments"]
