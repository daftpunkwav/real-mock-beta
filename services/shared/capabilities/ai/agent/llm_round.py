"""单轮 LLM 调用：流式优先、非流式回落，工具结果截断。

与主编排 ``loop.run_agent_loop`` 解耦：单轮调用/回落逻辑与工具结果截断规则
集中于此；循环的轮次推进、消息配对留在 ``loop.py``。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# 循环回调契约：execute 执行域工具；on_tool / on_thinking 为事件回调
ExecuteFn = Callable[[str, dict[str, Any]], Awaitable[str]]
OnToolFn = Callable[[str, dict[str, Any], str, str], Awaitable[None] | None]
OnThinkFn = Callable[[str], Awaitable[None] | None]

# 工具观察结果长度上限：超长截断并附后缀，避免污染后续轮次上下文
MAX_TOOL_RESULT_CHARS = 8_000


def _truncate_tool_result(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[truncated]"


async def _call_llm_round(
    llm: Any,
    call_messages: list[dict[str, Any]],
    *,
    temperature: float,
    tools: list[dict[str, Any]] | None,
    emit_thinking: OnThinkFn,
) -> dict[str, Any]:
    """一轮模型调用：优先流式（reasoning 增量实时回调），不支持时回落非流式。

    流式路径正文/工具调用由客户端组装成与非流式 ``chat_message`` 同构的
    message 事件返回；reasoning 增量已实时回调，不再重复取 ``reasoning`` 键。
    """
    streamer = getattr(llm, "chat_message_stream", None)
    if streamer is None:
        return await llm.chat_message(call_messages, temperature=temperature, tools=tools)
    try:
        msg: dict[str, Any] | None = None
        async for event in streamer(call_messages, temperature=temperature, tools=tools):
            etype = event.get("type")
            if etype == "reasoning":
                await emit_thinking(str(event.get("text") or ""))
            elif etype == "message":
                candidate = event.get("message")
                if isinstance(candidate, dict):
                    msg = candidate
        if msg is not None:
            return msg
        logger.warning("Agent 流式轮次未返回 message，回落非流式")
    except NotImplementedError:
        logger.info("LLM 不支持流式工具轮，回落非流式: %s", type(llm).__name__)
    return await llm.chat_message(call_messages, temperature=temperature, tools=tools)
