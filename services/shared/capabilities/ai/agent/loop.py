"""统一 Agent 循环：一步 = 一次 LLM 调用 + 本轮工具执行。

对齐 Pi ``agentLoop`` / DeepSeek Harness 的 step（model request + tools it calls）。
域工具以 OpenAI tools schema + ``execute`` 回调注册（harness「能力即插件」的精简形态），
不引入 Cordis、MCP、shell 或子 Agent。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from shared.capabilities.ai.llm.tool_args import parse_tool_arguments

logger = logging.getLogger(__name__)

ExecuteFn = Callable[[str, dict[str, Any]], Awaitable[str]]
OnToolFn = Callable[[str, dict[str, Any], str, str], Awaitable[None] | None]
OnThinkFn = Callable[[str], Awaitable[None] | None]

MAX_TOOL_RESULT_CHARS = 8_000


class AgentHalt(Exception):
    """工具要求立即终止循环（如 ask_user 等待用户输入）。

    message 会作为该工具的 observation 写回消息序列，
    保证 assistant.tool_calls 与 tool 结果一一对应。
    """

    def __init__(self, observation: str = ""):
        super().__init__(observation or "agent halted by tool")
        self.observation = observation or "agent halted by tool"


# 预算感知提示（对齐终端类 Agent 的收尾 nudge）：仅在最后一轮注入本次调用，
# 不写入 working——保证轮次耗尽前模型有机会收尾，而不是被硬截断。
_WRAP_UP_HINT = {
    "role": "system",
    "content": (
        "这是最后一轮工具调用机会：若信息已足够，请直接给出面向用户的完整回答，"
        "不要再调用工具；若仍缺关键信息，只调用最必要的一个工具。"
    ),
}

# 行动旁白纠偏提示（一次性，drift_retry=True 时启用）：模型尚未调用任何工具
# 就输出「我去搜一下…」式的短旁白即收尾——用户什么实际内容都没收到。注入
# 一次性纠偏提示重试一轮；模型坚持只给短旁白则按最终回答接受（有界，不死循环）。
_DRIFT_HINT = {
    "role": "system",
    "content": (
        "系统提示：你上一条消息宣布了要执行的操作，但没有调用任何工具，"
        "用户没有收到任何实际内容。请立即调用对应工具；若确实无需工具，"
        "直接给出面向用户的完整回答。"
    ),
}
# 短于此长度的无工具首轮正文视为行动旁白（完整辅导回答几乎不会这么短）
_DRIFT_MAX_CHARS = 200


def _join_thinking(parts: list[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


async def _call_llm_round(
    llm: Any,
    call_messages: list[dict[str, Any]],
    *,
    temperature: float,
    tools: list[dict[str, Any]] | None,
    emit_thinking: "OnThinkFn",
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
    halted: bool = False
    # 各轮模型 reasoning（思考过程）拼接，仅展示用；供应商未回传时为空串
    thinking: str = ""
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
    on_thinking: OnThinkFn | None = None,
    drift_retry: bool = False,
) -> LoopResult:
    """执行工具循环直到模型不再要工具，或达到 ``max_rounds``。

    模型一旦返回不带 tool_calls 的正文，该正文即最终回答（无论此前是否用过
    工具）——循环结束，调用方直接播报，不做无工具的二次生成（与终端类
    Agent 的收尾语义一致：模型停止行动 = 回合结束）。
    若调用过工具后模型只回 tool_calls 且达到 ``max_rounds``：``final_content``
    为 None，调用方可再生成收尾回答。同轮多个工具并行执行（结果按
    tool_calls 顺序回填，消息序列保持配对）。

    ``on_thinking``：模型 reasoning（思考过程）实时回调——每轮 LLM 调用优先
    走 ``chat_message_stream`` 流式（思考增量即时可见，避免长思考期间连接
    静默），客户端缺失或协议不支持时回落非流式（reasoning 随 message 一次
    性回传）；``drift_retry``：未调用任何工具的短旁白正文不作为最终回答，
    注入一次性纠偏提示重试一轮（仅当轮次尚有余量；模型坚持则照常接受）。
    """
    if not tools or max_rounds <= 0:
        return LoopResult(messages=list(messages), final_content=None, tool_used=False)

    working = list(messages)
    tool_used = False
    halted = False
    thinking_parts: list[str] = []
    thinking_emitted = False
    drift_corrected = False
    # 一次性提示（纠偏）暂存区：仅下一次 LLM 调用可见，不写入 working
    transient: list[dict[str, Any]] = []

    for round_i in range(max_rounds):
        call_messages = [*working, *transient]
        transient = []
        # 最后一轮注入收尾提示（仅本次调用可见，不写入 working 持久消息）
        if round_i == max_rounds - 1 and round_i > 0:
            call_messages.append(_WRAP_UP_HINT)

        round_thinking: list[str] = []

        async def emit_thinking(text: str) -> None:
            nonlocal thinking_emitted
            if not text:
                return
            # 展示通道：仅「新一轮的首段」补轮间分隔；持久化通道保留原始分段
            display = ("\n\n" + text) if (thinking_emitted and not round_thinking) else text
            thinking_emitted = True
            round_thinking.append(text)
            if on_thinking is not None:
                maybe = on_thinking(display)
                if maybe is not None:
                    await maybe

        try:
            msg = await _call_llm_round(
                llm,
                call_messages,
                temperature=temperature,
                tools=tools,
                emit_thinking=emit_thinking,
            )
        except Exception as e:
            logger.warning("Agent 循环 LLM 失败 round=%s: %s", round_i, e)
            break

        if not round_thinking:
            # 非流式路径：reasoning 随 message 一次性回传，此处补发
            reasoning = msg.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                await emit_thinking(reasoning)
        if round_thinking:
            thinking_parts.append("".join(round_thinking))

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            content = msg.get("content")
            text = str(content or "").strip()
            if (
                drift_retry
                and not tool_used
                and text
                and len(text) < _DRIFT_MAX_CHARS
                and not drift_corrected
                and round_i < max_rounds - 1
            ):
                drift_corrected = True
                transient = [_DRIFT_HINT]
                logger.info(
                    "Agent 检测到无工具行动旁白(round=%s, %s 字符),注入纠偏提示重试",
                    round_i,
                    len(text),
                )
                continue
            if content:
                return LoopResult(
                    messages=working,
                    final_content=str(content),
                    tool_used=tool_used,
                    thinking=_join_thinking(thinking_parts),
                )
            break

        tool_used = True
        limited = tool_calls[:max_tools_per_round]
        working.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": limited,
        })

        async def _run_one(tc: dict[str, Any]) -> tuple[str, bool]:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = parse_tool_arguments(fn.get("arguments"))
            try:
                result = await execute(name, args)
                return _truncate_tool_result(str(result or "")), False
            except AgentHalt as halt:
                return _truncate_tool_result(halt.observation), True
            except Exception as tool_exc:
                logger.warning("工具执行失败 tool=%s: %s", name, tool_exc)
                return f"工具执行失败: {tool_exc}", False

        outcomes = await asyncio.gather(*(_run_one(tc) for tc in limited))
        halted = False
        for tc, (result, did_halt) in zip(limited, outcomes):
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = parse_tool_arguments(fn.get("arguments"))
            tc_id = str(tc.get("id") or f"call_{round_i}_{name}")
            working.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result,
            })
            if on_tool is not None:
                maybe = on_tool(name, args, result, tc_id)
                if maybe is not None:
                    await maybe
            halted = halted or did_halt
        if halted:
            break

    return LoopResult(
        messages=working,
        final_content=None,
        tool_used=tool_used,
        halted=halted,
        thinking=_join_thinking(thinking_parts),
    )
