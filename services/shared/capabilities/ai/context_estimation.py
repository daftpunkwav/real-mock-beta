"""token 估算与纯文本 / digest 辅助（上下文压缩的机械基础）。

- ``estimate_tokens``：粗略估算（中文约 1.5 字符/token），仅用于预算检查；
- ``estimate_messages_tokens``：消息列表总 token（支持多模态 list content）；
- ``_plain_text`` / ``_omitted_digest``：被压缩对话的结构化摘要文本。
"""

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
