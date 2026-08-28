"""统一 Agent 循环：一步 = 一次 LLM 调用 + 本轮工具执行。

对齐 Pi ``agentLoop`` / DeepSeek Harness 的 step（model request + tools it calls）。
域工具以 OpenAI tools schema + ``execute`` 回调注册（harness「能力即插件」的精简形态），
不引入 Cordis、MCP、shell 或子 Agent。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from shared.capabilities.ai.llm.tool_args import parse_tool_arguments

logger = logging.getLogger(__name__)

ExecuteFn = Callable[[str, dict[str, Any]], Awaitable[str]]
OnToolFn = Callable[[str, dict[str, Any], str, str], Awaitable[None] | None]

MAX_TOOL_RESULT_CHARS = 8_000


def _truncate_tool_result(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[truncated]"


@dataclass
class LoopResult:
    """一轮或多步工具循环的结果。"""

    messages: list[dict[str, Any]]
    final_content: str | None
    tool_used: bool
    extras: dict[str, Any] = field(default_factory=dict)


async def run_agent_loop(
    llm: Any,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
    execute: ExecuteFn,
    max_rounds: int,
    max_tools_per_round: int = 8,
    temperature: float = 0.7,
    on_tool: OnToolFn | None = None,
) -> LoopResult:
    """执行工具循环直到模型不再要工具，或达到 ``max_rounds``。

    若首轮无 tool_calls 且已有 content：返回该 content，调用方无需二次 LLM。
    若调用过工具：``final_content`` 为 None，调用方可对流式生成最终回答。
    """
    if not tools or max_rounds <= 0:
        return LoopResult(messages=list(messages), final_content=None, tool_used=False)

    working = list(messages)
    tool_used = False

    for round_i in range(max_rounds):
        try:
            msg = await llm.chat_message(
                working,
                temperature=temperature,
                tools=tools,
            )
        except Exception as e:
            logger.warning("Agent 循环 LLM 失败 round=%s: %s", round_i, e)
            break

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            content = msg.get("content")
            if content and not tool_used:
                return LoopResult(
                    messages=working, final_content=str(content), tool_used=False
                )
            break

        tool_used = True
        limited = tool_calls[:max_tools_per_round]
        working.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": limited,
        })
        for tc in limited:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = parse_tool_arguments(fn.get("arguments"))
            tc_id = str(tc.get("id") or f"call_{round_i}_{name}")
            try:
                result = await execute(name, args)
            except Exception as tool_exc:
                logger.warning("工具执行失败 tool=%s: %s", name, tool_exc)
                result = f"工具执行失败: {tool_exc}"
            result = _truncate_tool_result(str(result or ""))
            working.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result,
            })
            if on_tool is not None:
                maybe = on_tool(name, args, result, tc_id)
                if maybe is not None:
                    await maybe

    return LoopResult(messages=working, final_content=None, tool_used=tool_used)
