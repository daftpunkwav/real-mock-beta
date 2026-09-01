"""上下文压缩与 token 估算（编排入口）。

规则压缩、LLM 纪要压缩与机械估算分别下沉到同目录分组模块：

- ``context_estimation``：token 估算与纯文本/digest 辅助
- ``context_compress``：规则 ``compress_messages`` + 工具对折叠
- ``context_summarize``：LLM 纪要式 ``compact_with_summary``

本文件保留公开函数与 ``prepare_llm_context`` 编排：压缩 + 注入工作记忆。
工作记忆作为独立 system 段注入，使模型在截断后仍看得到结构化事实。
"""

from __future__ import annotations

from typing import Any

from shared.capabilities.ai.agent.working_memory import MEMORY_MARKER, WorkingMemory
from shared.capabilities.ai.context_compress import (
    _COMPACTION_DIGEST_MARKER,
    _COMPACTION_SUMMARY_MARKER,
    compress_messages,
)
from shared.capabilities.ai.context_estimation import (
    estimate_messages_tokens,
    estimate_tokens,
)
from shared.capabilities.ai.context_summarize import compact_with_summary

__all__ = [
    "_COMPACTION_SUMMARY_MARKER",
    "_COMPACTION_DIGEST_MARKER",
    "estimate_tokens",
    "estimate_messages_tokens",
    "compress_messages",
    "compact_with_summary",
    "upsert_memory_block",
    "prepare_llm_context",
]


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
