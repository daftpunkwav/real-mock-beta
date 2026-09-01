"""LLM 纪要式压缩：``compact_with_summary``（终端类 Agent auto-compact 的离线等价）。

超阈值时把被省略对话交给 LLM 生成分节纪要，替换旧纪要（增量式：上一份
纪要作为输入，信息不丢）；LLM 失败回退规则摘要（记 warning，可见降级，
非静默）。``llm=None`` 等价规则压缩；未超阈值原样返回（仍做工具对折叠）。
"""

from __future__ import annotations

import logging
from typing import Any

from shared.capabilities.ai.agent.working_memory import WorkingMemory
from shared.capabilities.ai.context_compress import (
    _COMPACTION_DIGEST_MARKER,
    _COMPACTION_SUMMARY_MARKER,
    _prune_stale_tool_pairs,
)
from shared.capabilities.ai.context_estimation import _omitted_digest, _plain_text, estimate_messages_tokens

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "把历史对话压缩为供后续对话使用的结构化纪要。"
    "保留事实、决策、结论与未完成事项，丢弃寒暄、重复与过程性内容。"
    "按以下分节输出，每节一到两行，没有内容的分节省略：\n"
    "会话目标 / 已确认的关键决策 / 用户薄弱点与明确要求 / 重要发现与结论 / 待办与下一步\n"
    "禁止添加对话中不存在的内容。"
)


def _previous_summary_text(system: list[dict[str, Any]]) -> str:
    """取上一份 LLM 纪要正文（增量压缩的输入）；无则空串。"""
    for m in reversed(system):
        content = m.get("content")
        if (
            isinstance(content, str)
            and content.startswith(_COMPACTION_SUMMARY_MARKER)
        ):
            return content[len(_COMPACTION_SUMMARY_MARKER):].strip()
    return ""


async def _summarize_transcript(
    llm: Any,
    prior: str,
    omitted: list[dict[str, Any]],
) -> str:
    """让 LLM 生成（增量更新的）分节会话纪要。失败由调用方回退。"""
    parts: list[str] = []
    if prior:
        parts.append(f"上一份纪要（请在其基础上增量更新，不要丢失仍有效的信息）：\n{prior}")
    lines: list[str] = []
    for m in omitted:
        snippet = _plain_text(m.get("content")).replace("\n", " ").strip()
        if snippet:
            if len(snippet) > 200:
                snippet = snippet[:199] + "…"
            lines.append(f"{m.get('role')}: {snippet}")
    parts.append("需要压缩的对话：\n" + "\n".join(lines[:60]))
    summary = await llm.chat(
        [{"role": "user", "content": "\n\n".join(parts)}],
        temperature=0.2,
        max_tokens=800,
    )
    return str(summary or "").strip()


async def compact_with_summary(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    memory: WorkingMemory | None = None,
    llm: Any = None,
    keep_recent: int = 20,
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """LLM 纪要式压缩（终端类 Agent auto-compact 的离线等价）。

    超过阈值时：先折叠旧工具调用对，再把被省略对话交给 LLM 生成分节纪要，
    替换旧纪要（增量式：上一份纪要作为输入，信息不丢）。LLM 失败时回退
    规则摘要（记 warning，可见降级，非静默）。未超阈值原样返回。
    供具备 LLM 实例的 agent 在每轮开始时调用；``llm=None`` 时等价规则压缩。
    """
    system = [m for m in messages if m.get("role") == "system"]
    rest = _prune_stale_tool_pairs(
        [m for m in messages if m.get("role") != "system"]
    )
    # 旧工具对折叠无条件生效（微压缩）；LLM 纪要仅在超阈值时生成
    if max_tokens > 0 and estimate_messages_tokens(system + rest) <= max_tokens * threshold:
        return system + rest
    trimmed = rest[-keep_recent:]
    omitted = rest[: max(0, len(rest) - len(trimmed))]
    if memory is not None and omitted:
        memory.absorb_omitted(omitted)

    # 无可省略对话时纪要没有输入，直接走规则摘要路径
    summary_text = ""
    if omitted and llm is not None:
        try:
            summary_text = await _summarize_transcript(
                llm, _previous_summary_text(system), omitted
            )
        except Exception as e:
            logger.warning("LLM 会话纪要失败，回退规则摘要: %s", e)
            summary_text = ""

    if summary_text:
        kept_system = [
            m
            for m in system
            if not (
                isinstance(m.get("content"), str)
                and str(m.get("content")).startswith(
                    (_COMPACTION_SUMMARY_MARKER, _COMPACTION_DIGEST_MARKER)
                )
            )
        ]
        return kept_system + [
            {"role": "system", "content": f"{_COMPACTION_SUMMARY_MARKER} {summary_text}"}
        ] + trimmed

    digest = _omitted_digest(omitted)
    body = (
        f"[上下文压缩] 早期 {len(omitted)} 条对话已省略，"
        f"保留最近 {len(trimmed)} 条。"
    )
    if digest:
        body += "\n摘要：\n" + digest
    return system + [{"role": "system", "content": body}] + trimmed
