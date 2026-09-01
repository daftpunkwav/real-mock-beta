"""LLM JSON 输出解析：think 围栏剥离、代码围栏、容错重试。

``chat_json`` 的解析主体；失败仍由调用方（report 等）看见异常——本模块
不吞错、不返回假 JSON。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


async def parse_chat_json(
    chat_fn: Callable[..., Awaitable[str]],
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    """请求 JSON 格式响应并解析。

    ``chat_fn`` 是对客户端 ``chat`` 的绑定（response_format 由本模块指定）；
    ``max_tokens`` 需按输出体量给足（如简历深度评价的完整 JSON 超过
    默认 4096 上限，截断会导致 JSON 解析失败）。
    """
    content = await chat_fn(
        messages,
        temperature=temperature,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    if not (isinstance(content, str) and content.strip()):
        logger.warning("chat_json 首次返回空，回退无 response_format 重试")
        retry_messages = list(messages)
        retry_messages.append({
            "role": "user",
            "content": "请只输出一个合法 JSON 对象，不要 Markdown，不要解释。",
        })
        content = await chat_fn(retry_messages, temperature=temperature)
    if content is None or (isinstance(content, str) and not content.strip()):
        raise ValueError(
            "LLM 返回空内容，无法解析 JSON。"
            "请确认模型支持 Chat Completions 文本输出（当前可能使用了仅推理/空 content 的模型）。"
        )
    text = content if isinstance(content, str) else str(content)
    text = text.strip()
    for open_t, close_t in (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
    ):
        while True:
            lo = text.lower().find(open_t)
            if lo < 0:
                break
            hi = text.lower().find(close_t, lo + len(open_t))
            if hi < 0:
                text = text[:lo] + text[lo + len(open_t) :]
                break
            text = text[:lo] + text[hi + len(close_t) :]
    from .openai_transport import strip_code_fences

    text = strip_code_fences(text)
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # LLM 长 JSON 两类高频语法错误:尾随逗号(,} / ,])与字符串内
        # 裸控制字符(未转义换行/制表符);剥离/转义后重试一次
        from .openai_transport import repair_common_json_errors

        data = json.loads(repair_common_json_errors(text))
    if not isinstance(data, dict):
        raise ValueError("LLM JSON 根类型必须是 object")
    return data


__all__ = ["parse_chat_json"]
