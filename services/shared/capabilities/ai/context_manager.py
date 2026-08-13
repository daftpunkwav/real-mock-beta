"""上下文压缩与 token 估算。"""

from __future__ import annotations

from typing import Any


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


def compress_messages(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    keep_recent: int = 20,
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """超过预算时压缩为 system 消息 + 最近 N 条对话。

    策略：
    - 总是保留所有 ``system`` 消息（面试规则、追问引导等不可丢失）。
    - 只在 ``total > max_tokens * threshold`` 时触发，避免过度压缩；
      阈值默认 0.3（30%）以让长会话尽快进入摘要流程，防止 token 堆叠爆窗。
    - 用户/助手对话仅保留最近 ``keep_recent`` 条。
    """
    total = estimate_messages_tokens(messages)
    if total <= max_tokens * threshold:
        return messages

    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    trimmed = rest[-keep_recent:]

    # 在 system 段末尾追加压缩说明，让 LLM 知道上下文被截断
    summary = {
        "role": "system",
        "content": (
            f"[上下文压缩] 早期 {len(rest) - len(trimmed)} 条对话已省略，"
            f"保留最近 {len(trimmed)} 条。"
        ),
    }
    return system + [summary] + trimmed
