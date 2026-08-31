"""say-first 协议解析：工具轮 early 文本的非流式解析 + 流式增量解析。

从 :mod:`interview_service.services.interview.runner` 拆出，三个流式入口共用。
think 剥离在前、协议解析在后，两层独立；降级（未按协议输出）时
``TurnOutput.say`` 为全部可见文本，控制字段走默认值。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from interview_service.services.interview.agent_text import (
    ThinkStreamFilter,
    strip_think_blocks,
)
from interview_service.services.interview.events import StreamEvent
from interview_service.services.interview.turn_output import TurnOutput, parse_turn_output
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.ai.llm.say_first_stream import SayFirstStreamParser


def parse_complete_output(text: str) -> TurnOutput:
    """非流式路径（工具轮 early 文本）的 say-first 解析与降级。

    工具轮里模型直接给出文本回答时，正文同样遵循 say-first 协议；
    整体解析失败时把原文当 say（与流式降级语义一致）。
    """
    visible = strip_think_blocks(text or "")
    try:
        parsed = json.loads(visible.strip())
    except Exception:
        return parse_turn_output(None, say_text=visible, degraded=True)
    if isinstance(parsed, dict) and isinstance(parsed.get("say"), str):
        return parse_turn_output(parsed, say_text=parsed["say"])
    return parse_turn_output(None, say_text=visible, degraded=True)


async def stream_say_first(
    llm: LLMClient,
    tools: Any,
    api_messages: list[dict[str, Any]],
    *,
    temperature: float,
) -> AsyncIterator[StreamEvent | TurnOutput]:
    """流式调用 LLM 并按 say-first 协议解析。

    ``tools`` 需暴露 ``collect_chat_tools``（即 :class:`ToolRoundRunner`）。
    产出 TOKEN 事件（say 明文增量），末尾 yield TurnOutput 供调用方收尾。
    """
    think_filter = ThinkStreamFilter()
    parser = SayFirstStreamParser()
    say_parts: list[str] = []
    stream_tools = tools.collect_chat_tools(include_function_tools=False)
    async for token in llm.chat_stream(
        api_messages, temperature=temperature, tools=stream_tools
    ):
        visible = think_filter.feed(token or "")
        if not visible:
            continue
        say_chunk = parser.feed(visible)
        if say_chunk:
            say_parts.append(say_chunk)
            yield StreamEvent.make_token(say_chunk)
    tail = parser.finish()
    if tail:
        say_parts.append(tail)
        yield StreamEvent.make_token(tail)
    say_text = parser.raw_text if parser.degraded else "".join(say_parts)
    yield parse_turn_output(
        parser.controls,
        say_text=say_text,
        degraded=parser.degraded,
    )


__all__ = ["parse_complete_output", "stream_say_first"]
