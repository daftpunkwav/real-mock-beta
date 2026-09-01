"""规则压缩：``compress_messages`` 与旧工具对折叠。

- ``_prune_stale_tool_pairs``：折叠最近一条用户消息之前的工具调用对
  （assistant.tool_calls + tool 结果从上下文移除，旧工具观察动辄数千
  token，结论已由工作记忆/纪要承载；最近一轮原样保留，保证协议配对）；
- ``compress_messages``：system 全保 + 最近 N 条 + 摘要行。
"""

from __future__ import annotations

from typing import Any

from shared.capabilities.ai.agent.working_memory import WorkingMemory
from shared.capabilities.ai.context_estimation import (
    _omitted_digest,
    estimate_messages_tokens,
)

# 压缩产物标记（system 消息前缀）；新纪要生成后旧标记消息被替换
_COMPACTION_SUMMARY_MARKER = "[会话纪要]"
_COMPACTION_DIGEST_MARKER = "[上下文压缩]"


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
