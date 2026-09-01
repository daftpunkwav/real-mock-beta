"""Prep 聊天编排：同步单轮、SSE 事件流、落库收尾。

从 ``agent`` 主文件拆出的「对话层」：``run_chat`` / ``run_chat_stream``
驱动工具轮并回放最终回答，``finalize`` / ``polish_final`` / ``usage_event``
负责落库净化。工具循环（``_run_tool_rounds``）与上下文组装仍留在
:mod:`agent`。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from shared.capabilities.ai.context_manager import (
    estimate_tokens,
    prepare_llm_context,
)
from shared.capabilities.ai.llm.stream_filters import sanitize_special_tokens

from .ask_user import _ASK_USER_FALLBACK_REPLY, _extract_inline_ask_user
from .streaming import slice_stream, stream_tool_rounds

if TYPE_CHECKING:
    from .agent import PrepAgent

# 落库思考长度上限（展示用元数据）
_MAX_PERSISTED_THINKING_CHARS = 20_000


def finalize(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    final: str,
    db: Session,
    *,
    tool_steps: list[dict[str, Any]] | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    thinking: str | None = None,
) -> None:
    """落库：追加 assistant 消息（含步骤/检索卡片/思考元数据）、规则压缩、更新 token 统计。"""
    agent.messages = working
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": final}
    # 仅展示用元数据;LLM client 只取 role/content,不会进入模型上下文
    if tool_steps:
        assistant_msg["steps"] = tool_steps
    if search_groups:
        assistant_msg["search_groups"] = search_groups
    combined = (thinking or "").strip()
    if combined:
        assistant_msg["thinking"] = combined[:_MAX_PERSISTED_THINKING_CHARS]
    agent.messages.append(assistant_msg)
    if final:
        agent.memory.remember("asked", final)
    agent.messages = prepare_llm_context(agent.messages, agent.context_window, memory=agent.memory)
    agent.session.token_usage = sum(
        estimate_tokens(str(m.get("content", ""))) for m in agent.messages
    )
    # 真实用量累计（供应商回传时可得；估算值仅用于圆环占比）
    usage = getattr(agent.llm, "usage", None)
    if usage is not None:
        agent.session.prompt_tokens = (agent.session.prompt_tokens or 0) + usage.prompt_tokens
        agent.session.completion_tokens = (
            agent.session.completion_tokens or 0
        ) + usage.completion_tokens
        agent.session.cached_tokens = (agent.session.cached_tokens or 0) + usage.cached_tokens
    agent._save(db)


def polish_final(text: str) -> tuple[str, dict[str, Any] | None]:
    """出站净化：内联 ask_user 抢救 + 特殊 token/内联工具块清洗。返回 ``(正文, ask 事件或 None)``。"""
    cleaned, ask_event = _extract_inline_ask_user(text or "")
    return sanitize_special_tokens(cleaned).strip(), ask_event


def usage_event(agent: "PrepAgent") -> dict[str, Any] | None:
    """本轮 LLM 用量事件；供应商未回传时不发。"""
    usage = getattr(agent.llm, "usage", None)
    if usage is None or not (usage.prompt_tokens or usage.completion_tokens):
        return None
    return {"type": "usage", **usage.to_dict()}


async def run_chat(agent: "PrepAgent", user_text: str, db: Session) -> str:
    agent._ensure_system(db)
    agent.messages.append({"role": "user", "content": user_text})
    working = await agent._build_context()

    asked_user: dict[str, bool] = {"on": False}
    working, early, groups, steps, thinking = await agent._run_tool_rounds(
        working, db, asked_user=asked_user
    )
    if asked_user["on"]:
        # 弹窗已展示:与流式路径一致,等待用户作答,不再编造回答
        final = _ASK_USER_FALLBACK_REPLY
    elif early:
        # 模型收尾正文即最终回答;非流式通道无法下发弹窗事件,仅做净化
        final, _ = polish_final(early)
        final = final or _ASK_USER_FALLBACK_REPLY
    else:
        final = await agent.llm.chat(working, temperature=0.7)

    finalize(
        agent, working, final, db, tool_steps=steps, search_groups=groups, thinking=thinking
    )
    return final


async def run_chat_stream(
    agent: "PrepAgent", user_text: str, db: Session
) -> AsyncIterator[str | dict[str, Any]]:
    """ReAct 工具循环（事件即时推送）→ 再流式输出最终回答。

    产出 ``str``（正文 token）或 ``dict``（``status`` / ``thinking`` /
    ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` 事件）。
    """
    agent._ensure_system(db)
    agent.messages.append({"role": "user", "content": user_text})
    working = await agent._build_context()

    yield {"type": "status", "text": "正在分析问题…"}
    await asyncio.sleep(0)

    events: asyncio.Queue = asyncio.Queue()
    asked_user: dict[str, bool] = {"on": False}
    outcome: dict[str, Any] = {}
    async for item in stream_tool_rounds(
        agent._run_tool_rounds, outcome, events, working, db, asked_user=asked_user
    ):
        yield item

    early: str | None = None
    search_groups: list[dict[str, Any]] = []
    tool_steps: list[dict[str, Any]] = []
    thinking: str = ""
    value = outcome.get("value")
    if isinstance(value, tuple) and len(value) == 5:
        working, early, search_groups, tool_steps, thinking = value

    if asked_user["on"]:
        # 弹窗事件与检索卡片已在工具执行时即时推送;此处仅清状态行收尾
        yield {"type": "status", "text": ""}
        final = _ASK_USER_FALLBACK_REPLY
        async for piece in slice_stream(final):
            yield piece
        finalize(agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups, thinking=thinking)
        event = usage_event(agent)
        if event:
            yield event
        return

    if search_groups:
        yield {"type": "search_results", "groups": search_groups}
        yield {"type": "status", "text": "正在整理检索要点…"}
        await asyncio.sleep(0)

    # 正文开始:清除状态行
    yield {"type": "status", "text": ""}
    if early:
        # 模型收尾正文即最终回答(可能伴随内联 ask_user 漂移):先净化抢救再切片回放
        final, inline_ask = polish_final(early)
        if final:
            async for piece in slice_stream(final):
                yield piece
        if inline_ask is not None:
            # 抢救成真实弹窗：正文给出上下文后弹出选择框
            yield {"type": "ask_user", **inline_ask}
            final = final or _ASK_USER_FALLBACK_REPLY
    else:
        # 兜底：循环未产出正文（轮次耗尽/LLM 异常），无工具流式生成收尾回答
        final = ""
        async for token in agent.llm.chat_stream(working, temperature=0.7):
            final += token
            yield token

    event = usage_event(agent)
    finalize(agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups, thinking=thinking)
    if event:
        yield event


__all__ = [
    "_MAX_PERSISTED_THINKING_CHARS",
    "finalize",
    "polish_final",
    "run_chat",
    "run_chat_stream",
    "usage_event",
]
