"""Prep 域工具注册表：定义与执行同址，新增工具只改本文件。

每个工具一条 :class:`ToolSpec`（OpenAI tools schema + handler），
``PREP_TOOL_DEFINITIONS`` 由注册表派生，``execute_prep_tool`` 统一分发。
Agent 编排层（agent.py）只面向注册表，不感知具体工具——扩展工具无需
改动 ReAct 循环或 agent。

handler 签名：``(args: dict, memory: WorkingMemory) -> (observation, search_hits)``。
需要用户输入或改变控制流的工具（如 ask_user）不走注册表，由 agent 单独处理。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from shared.capabilities.ai.agent import WorkingMemory
from shared.capabilities.ai.llm.client.tool_args import parse_tool_arguments
from shared.capabilities.integrations.github.tools import (
    GITHUB_TOOL_DEFINITIONS,
    execute_github_tool,
)
from shared.catalogs.company import get_company_context
from shared.capabilities.knowledge.search.web import SearchHit, web_search_with_hits

SearchHits = list[SearchHit]
ToolHandler = Callable[[dict[str, Any], WorkingMemory], Awaitable[tuple[str, SearchHits]]]

_WEB_SEARCH_MAX_RESULTS = 3

_PREP_GITHUB_NAMES = frozenset({
    "github_list_repos",
    "github_get_readme",
    "github_get_repo",
    "github_list_commits",
    "github_get_user",
})


@dataclass(frozen=True)
class ToolSpec:
    """一个域工具的完整声明：schema + 执行体。"""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


async def _run_web_search(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    query = str(args.get("query", "") or "")
    if query:
        memory.remember("note", f"检索:{query}")
    text, hits = await asyncio.to_thread(
        web_search_with_hits, query, _WEB_SEARCH_MAX_RESULTS
    )
    return text, hits


async def _run_company_info(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    del memory
    company = str(args.get("company", "") or "")
    return await asyncio.to_thread(get_company_context, company), []


async def _run_quiz(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    question = str(args.get("question", "") or "")
    qtype = str(args.get("type", "open") or "open")
    memory.remember("quiz", f"{qtype}:{question}")
    return (
        f"已记下练习题，请在正式回答中出题并等待用户作答：{question}（{qtype}）",
        [],
    )


async def _run_take_note(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    kind = str(args.get("kind", "note") or "note")
    content = str(args.get("content", "") or "").strip()
    if not content:
        return "take_note 缺少 content，未记录。", []
    memory.remember("weak" if kind == "weak_point" else "note", content)
    return f"已写入工作记忆（{kind}）：{content}", []


def _github_tool_spec(name: str) -> ToolSpec:
    raw = next(
        t for t in GITHUB_TOOL_DEFINITIONS
        if (t.get("function") or {}).get("name") == name
    )
    fn = raw["function"]

    async def handler(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
        del memory
        return await execute_github_tool(name, args), []

    return ToolSpec(
        name=name,
        description=str(fn.get("description") or ""),
        parameters=dict(fn.get("parameters") or {"type": "object"}),
        handler=handler,
    )


# 注册表：Prep 可用工具的唯一事实来源（ask_user 等控制流工具不在此列）
_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="web_search",
        description="搜索公开面经/技术资料。仅在需要补充时效信息时使用。",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=_run_web_search,
    ),
    ToolSpec(
        name="company_info",
        description="查询目标公司的面试风格、考察重点与样例问题。",
        parameters={
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "公司 id，如 bytedance / tencent",
                },
            },
            "required": ["company"],
        },
        handler=_run_company_info,
    ),
    ToolSpec(
        name="quiz",
        description="向候选人出一道练习题（选择题或开放题）。",
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["choice", "open"],
                    "description": "题目类型",
                },
            },
            "required": ["question"],
        },
        handler=_run_quiz,
    ),
    ToolSpec(
        name="take_note",
        description=(
            "把要点写入会话工作记忆（后续轮次仍可见）："
            "用户暴露的薄弱点、确认的目标岗位/公司、重要结论。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["note", "weak_point"],
                    "description": "note=一般要点，weak_point=用户薄弱点",
                },
                "content": {"type": "string"},
            },
            "required": ["kind", "content"],
        },
        handler=_run_take_note,
    ),
] + [_github_tool_spec(name) for name in sorted(_PREP_GITHUB_NAMES)]

# name -> spec（冻结视图，供 agent 层查表）
TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in _TOOL_SPECS}

# OpenAI tools 格式定义（顺序稳定，直接下发模型）
PREP_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }
    for spec in _TOOL_SPECS
]


async def execute_prep_tool(
    name: str, args: dict[str, Any], memory: WorkingMemory
) -> tuple[str, SearchHits]:
    """按注册表分发工具；返回 ``(observation_text, search_hits)``。

    入参容忍 LLM 产出的字符串形态 JSON（与循环层同源解析）。
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return f"未知工具：{name}", []
    if not isinstance(args, dict):
        args = parse_tool_arguments(args)
    return await spec.handler(args, memory)


__all__ = [
    "PREP_TOOL_DEFINITIONS",
    "TOOL_REGISTRY",
    "ToolSpec",
    "execute_prep_tool",
    # 便于测试按模块路径替换
    "web_search_with_hits",
]
