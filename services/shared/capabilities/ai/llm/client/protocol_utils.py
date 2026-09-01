"""LLM 协议转译共享小工具。

各协议转换模块（anthropic / responses / 响应提取）共用的纯函数
（``_json_arguments``、``_headers``）；不承载任何协议专有逻辑。
"""

from __future__ import annotations

import json
from typing import Any

from shared.core.constants import LLMProtocol


def _json_arguments(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except TypeError:
        return "{}"


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


__all__ = ["_json_arguments", "_headers"]
