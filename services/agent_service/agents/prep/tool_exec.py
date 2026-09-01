"""Prep 工具执行回调构造：ask_user 分发、同参短路、超时与检索失败约束。

编排层（:mod:`agent`）在工具轮次里用 :func:`build_execute_callback` 构造
ReAct ``execute`` 回调；域工具本身的定义与执行仍见 :mod:`tools`。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session

from shared.capabilities.ai.agent import WorkingMemory
from shared.capabilities.knowledge.search.web import SearchHit

from .ask_user import dispatch_ask_user

logger = logging.getLogger(__name__)

_TOOL_TIMEOUT_SEC = 18.0

ToolRunner = Callable[[str, dict[str, Any], Session], Awaitable[tuple[str, list[SearchHit]]]]
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


def build_execute_callback(
    *,
    run_named_tool: ToolRunner,
    memory: WorkingMemory,
    db: Session,
    search_groups: list[dict[str, Any]],
    events: asyncio.Queue | None,
    asked_user: dict[str, bool] | None,
) -> ToolExecutor:
    """构造工具执行回调；``events``/``asked_user`` 供流式通道即时上报。

    本轮内对相同参数的重复调用直接短路（ReAct 防空转）；
    失败/超时的调用不缓存，允许换参数重试。
    """
    attempted: dict[str, str] = {}

    async def execute(name: str, args: dict[str, Any]) -> str:
        if name == "ask_user":
            return await dispatch_ask_user(
                question=args.get("question"),
                raw_options=args.get("options") or [],
                memory=memory,
                events=events,
                search_groups=search_groups,
                asked_user=asked_user,
            )
        query = args.get("query") or args.get("company") or args.get("repo") or ""
        header = f"[{name}] {query}".strip()
        key = name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        if key in attempted:
            return (
                "重复调用已跳过（与此前调用参数相同）。"
                "请直接基于已有观察继续回答；确需重试请更换参数。"
            )
        attempted[key] = ""
        try:
            obs, hits = await asyncio.wait_for(
                run_named_tool(name, args, db),
                timeout=_TOOL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("工具超时 %s (%.0fs)", name, _TOOL_TIMEOUT_SEC)
            attempted.pop(key, None)
            obs = (
                "SEARCH_UNAVAILABLE\n"
                f"搜索超时（>{_TOOL_TIMEOUT_SEC:.0f}s）。请勿编造结果；可基于通用知识继续。"
            )
            hits = []
        if name == "web_search" and hits:
            search_groups.append({"query": str(query or ""), "results": hits})
        if "SEARCH_UNAVAILABLE" in obs or "搜索暂时不可用" in obs:
            attempted.pop(key, None)
            obs += (
                "\n\n【系统约束】检索未成功。禁止编造「搜索到的结果」清单、链接或引用；"
                "请用通用知识继续辅导，并写明「基于通用知识整理，非实时搜索」。"
            )
            return f"{header}\n{obs}"
        attempted[key] = f"{header}\n{obs}"
        return f"{header}\n{obs}"

    return execute


__all__ = ["build_execute_callback"]
