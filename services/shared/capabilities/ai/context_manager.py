"""上下文压缩与 token 估算。

- ``compress_messages``：规则压缩（system 全保 + 最近 N 条 + 摘要行）；
- ``compact_with_summary``：LLM 纪要式压缩（对齐终端类 Agent 的 auto-compact），
  超阈值时把被省略对话总结为分节纪要，失败回退规则摘要（记日志，不静默）；
- 两者共享「旧工具对折叠」：最近一条用户消息之前的 assistant.tool_calls 与
  tool 结果从上下文移除——旧工具观察动辄数千 token，结论已由工作记忆/纪要承载。

工作记忆作为独立 system 段注入，使模型在截断后仍看得到结构化事实。
"""

from __future__ import annotations

import logging
from typing import Any

from shared.capabilities.ai.agent.working_memory import MEMORY_MARKER, WorkingMemory

logger = logging.getLogger(__name__)

# 压缩产物标记（system 消息前缀）；新纪要生成后旧标记消息被替换
_COMPACTION_SUMMARY_MARKER = "[会话纪要]"
_COMPACTION_DIGEST_MARKER = "[上下文压缩]"


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字符/token）。

    仅用于预算检查；不追求与具体 tokenizer 完全一致。
    """
    if not text:
        return 0
    return max(1, int(len(text) / 1.5))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """估算消息列表总 token 数。

    支持多模态 ``content``:当 ``content`` 为 ``list`` 时,逐项累加文本片段。
    """
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    total += estimate_tokens(str(item.get("text", "")))
                else:
                    total += estimate_tokens(str(item))
        elif content is None:
            continue
        else:
            total += estimate_tokens(str(content))
    return total


def _plain_text(content: Any) -> str:
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return " ".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


def _message_lines(omitted: list[dict[str, Any]], role: str, *, clip: int = 80) -> list[str]:
    lines: list[str] = []
    for m in omitted:
        if m.get("role") != role:
            continue
        snippet = _plain_text(m.get("content")).replace("\n", " ").strip()
        if not snippet:
            continue
        if len(snippet) > clip:
            snippet = snippet[: clip - 1] + "…"
        lines.append(snippet)
    return lines


def _omitted_digest(omitted: list[dict[str, Any]], *, max_lines: int = 16) -> str:
    """被压缩对话的结构化摘要（对齐终端类 Agent 的分节压缩纪要）。

    分「用户诉求 / 已给结论」两节，各保留头部与尾部片段：头部是会话起因，
    尾部是最近语境，中间的低区分度轮次以条数带过。
    """
    user_lines = _message_lines(omitted, "user")
    assistant_lines = _message_lines(omitted, "assistant")
    sections: list[str] = []

    def _window(lines: list[str], head: int, tail: int) -> list[str]:
        if len(lines) <= head + tail:
            return lines
        kept = lines[:head] + lines[len(lines) - tail :]
        skipped = len(lines) - head - tail
        return kept[:head] + [f"（…中间省略 {skipped} 条…）"] + kept[head:]

    if user_lines:
        sections.append("用户诉求（早期）：\n" + "\n".join(f"- {l}" for l in _window(user_lines, 2, 3)))
    if assistant_lines:
        sections.append("已给结论（早期）：\n" + "\n".join(f"- {l}" for l in _window(assistant_lines, 0, 2)))
    if not sections:
        return ""
    return "\n".join(sections)[: max_lines * 90]


def _prune_stale_tool_pairs(rest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """折叠最近一条用户消息之前的工具调用对（assistant.tool_calls + tool 结果）。

    最近一轮原样保留，保证 OpenAI 协议下 tool_calls 与 tool 结果配对完整；
    更早轮次只保留带正文的 assistant 消息（丢弃 tool_calls 结构）。
    """
    last_user = -1
    for i, m in enumerate(rest):
        if m.get("role") == "user":
            last_user = i
    out: list[dict[str, Any]] = []
    for i, m in enumerate(rest):
        if i >= last_user:
            out.append(m)
            continue
        role = m.get("role")
        if role == "tool":
            continue
        if role == "assistant" and m.get("tool_calls"):
            if m.get("content"):
                out.append({"role": "assistant", "content": m["content"]})
            continue
        out.append(m)
    return out


def compress_messages(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    keep_recent: int = 20,
    threshold: float = 0.3,
    memory: WorkingMemory | None = None,
) -> list[dict[str, Any]]:
    """超过预算时压缩为 system 消息 + 最近 N 条对话。

    策略：
    - 总是保留所有 ``system`` 消息（面试规则、追问引导等不可丢失）。
    - 先折叠旧工具调用对，再按 ``total > max_tokens * threshold`` 判定是否
      需要进一步压缩（阈值默认 0.3，让长会话尽快进入摘要流程防止爆窗）。
    - 用户/助手对话仅保留最近 ``keep_recent`` 条。
    - 被省略的 user/assistant 写入摘要行；若传入 ``memory`` 则同时吸收到工作记忆。
    """
    system = [m for m in messages if m.get("role") == "system"]
    rest = _prune_stale_tool_pairs(
        [m for m in messages if m.get("role") != "system"]
    )
    # 旧工具对折叠无条件生效（微压缩）；进一步压缩仅在超阈值时进行
    if max_tokens > 0 and estimate_messages_tokens(system + rest) <= max_tokens * threshold:
        return system + rest

    trimmed = rest[-keep_recent:]
    omitted = rest[: max(0, len(rest) - len(trimmed))]
    if memory is not None and omitted:
        memory.absorb_omitted(omitted)

    digest = _omitted_digest(omitted)
    summary_body = (
        f"[上下文压缩] 早期 {len(omitted)} 条对话已省略，"
        f"保留最近 {len(trimmed)} 条。"
    )
    if digest:
        summary_body += "\n摘要：\n" + digest
    summary = {"role": "system", "content": summary_body}
    return system + [summary] + trimmed


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


def upsert_memory_block(    messages: list[dict[str, Any]],
    memory: WorkingMemory | None,
) -> list[dict[str, Any]]:
    """去掉旧工作记忆段，按当前 ``WorkingMemory`` 重新插入。"""
    out = [
        m
        for m in messages
        if not (
            m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(MEMORY_MARKER)
        )
    ]
    if memory is None:
        return out
    if not memory.render() and not memory.pending_quiz:
        return out
    out.append({"role": "system", "content": memory.dump_block()})
    return out


def prepare_llm_context(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    memory: WorkingMemory | None = None,
    keep_recent: int = 20,
) -> list[dict[str, Any]]:
    """发给模型前的上下文组装：压缩 + 注入工作记忆。"""
    if max_tokens <= 0:
        compacted = list(messages)
    else:
        compacted = compress_messages(
            messages, max_tokens, keep_recent=keep_recent, memory=memory
        )
    return upsert_memory_block(compacted, memory)
