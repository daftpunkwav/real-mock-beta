"""上下文压缩与 token 估算。

Pi 的 ``transformContext``：压缩 transcript，并把工作记忆作为独立 system 段注入，
使模型在截断后仍看得到结构化事实。
"""

from __future__ import annotations

from typing import Any

from shared.capabilities.ai.agent.working_memory import MEMORY_MARKER, WorkingMemory


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


def _omitted_digest(omitted: list[dict[str, Any]], *, max_lines: int = 16) -> str:
    lines: list[str] = []
    for m in omitted:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        snippet = _plain_text(m.get("content")).replace("\n", " ").strip()
        if not snippet:
            continue
        if len(snippet) > 80:
            snippet = snippet[:79] + "…"
        lines.append(f"- {role}: {snippet}")
        if len(lines) >= max_lines:
            break
    return "\n".join(lines)


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
    - 只在 ``total > max_tokens * threshold`` 时触发，避免过度压缩；
      阈值默认 0.3（30%）以让长会话尽快进入摘要流程，防止 token 堆叠爆窗。
    - 用户/助手对话仅保留最近 ``keep_recent`` 条。
    - 被省略的 user/assistant 写入摘要行；若传入 ``memory`` 则同时吸收到工作记忆。
    """
    total = estimate_messages_tokens(messages)
    if total <= max_tokens * threshold:
        return messages

    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
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


def upsert_memory_block(
    messages: list[dict[str, Any]],
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
