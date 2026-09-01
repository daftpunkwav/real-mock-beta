"""Prep 流式辅助：early 正文切片回放 + 工具轮 produce 队列。

编排层（:mod:`agent` 的 ``chat_stream``）用 :func:`stream_tool_rounds`
在后台跑工具轮并把事件队列透传，正文切片用 :func:`slice_stream`。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

# early 内容切片回放：模拟逐段输出，避免整段瞬显
_EARLY_SLICE_CHARS = 48
_EARLY_SLICE_DELAY = 0.02

# produce 协程结束哨兵（chat_stream 的事件队列用）
_PRODUCE_DONE = object()


def event_loopbacks(
    events: asyncio.Queue | None,
    on_tool_step: Any | None = None,
) -> tuple[Any, Any]:
    """构造工具循环的事件回调：思考增量与工具步进即时下发前端。

    ``on_tool_step`` 可选：收到工具步进时同步记录（如写入落库用的
    ``tool_steps`` 列表）。返回 ``(on_thinking, on_tool)``；``events`` 为
    None 时回调为空操作（非流式通道无需下发事件）。
    """
    async def on_thinking(text: str) -> None:
        # 模型思考增量（流式轮次逐段 / 非流式整段）：事件即时下发前端
        if events is not None:
            await events.put({"type": "thinking", "content": text})

    async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
        query = (
            args.get("query")
            or args.get("company")
            or args.get("repo")
            or args.get("question")
            or args.get("content")
            or ""
        )
        step = {"name": name, "query": str(query)[:120]}
        if on_tool_step is not None:
            on_tool_step(step)
        if events is not None:
            await events.put({"type": "tool_step", **step})

    return on_thinking, on_tool


def slice_stream(text: str) -> AsyncIterator[str]:
    """把一次性拿到的话题内容按小片回放，保证前端平滑显示。"""
    async def _gen() -> AsyncIterator[str]:
        for k in range(0, len(text), _EARLY_SLICE_CHARS):
            yield text[k : k + _EARLY_SLICE_CHARS]
            if k + _EARLY_SLICE_CHARS < len(text):
                await asyncio.sleep(_EARLY_SLICE_DELAY)
    return _gen()


async def stream_tool_rounds(
    run: Any,
    outcome: dict[str, Any],
    events: asyncio.Queue,
    *args: Any,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """后台执行一轮工具循环并透传其事件队列，直到 ``_PRODUCE_DONE`` 哨兵。

    ``run`` 以 ``events=events`` 注入（工具步进/思考/弹窗事件实时入队）；
    返回值写入 ``outcome["value"]``（异常写入 ``outcome["error"]``），供
    调用方在流结束后取用。与旧逻辑一致：工具轮失败不中断流式。
    """
    async def produce() -> None:
        try:
            outcome["value"] = await run(*args, events=events, **kwargs)
        except Exception as e:
            logger.warning("Prep 工具轮异常: %s", e)
            outcome["error"] = e
        await events.put(_PRODUCE_DONE)

    task = asyncio.create_task(produce())
    try:
        while True:
            item = await events.get()
            if item is _PRODUCE_DONE:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()


__all__ = [
    "_PRODUCE_DONE",
    "event_loopbacks",
    "slice_stream",
    "stream_tool_rounds",
]
