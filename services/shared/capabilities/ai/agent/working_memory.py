"""Agent 工作记忆：压缩后仍注入模型可见上下文。

对齐 Pi ``transformContext``（每步组装可见上下文）与 Codex 的「会话记忆与 transcript 分离」：
结构化事实单独保存，不依赖被截断的逐字对话。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_MAX_LIST = 16
_ITEM_CHARS = 160

MEMORY_MARKER = "[工作记忆]"


def _clip(text: str, n: int = _ITEM_CHARS) -> str:
    s = (text or "").strip().replace("\n", " ")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _bounded_append(items: list[str], value: str, limit: int = _MAX_LIST) -> None:
    v = _clip(value)
    if not v:
        return
    if v in items:
        return
    items.append(v)
    if len(items) > limit:
        del items[:-limit]


@dataclass
class WorkingMemory:
    """本会话工作记忆（面试 / 准备共用结构，字段按域选用）。"""

    asked: list[str] = field(default_factory=list)
    weak_points: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pending_quiz: str = ""

    @classmethod
    def from_state(cls, state: dict[str, Any] | None) -> WorkingMemory:
        raw = state or {}
        asked = [str(x) for x in (raw.get("asked_questions") or []) if x]
        weak = [str(x) for x in (raw.get("weak_points") or []) if x]
        findings: list[str] = []
        for f in raw.get("github_findings") or []:
            if isinstance(f, dict):
                findings.append(_clip(f"{f.get('tool', '')}: {f.get('preview', '')}"))
            elif f:
                findings.append(_clip(str(f)))
        notes = [str(x) for x in (raw.get("memory_notes") or []) if x]
        quiz = str(raw.get("pending_quiz") or "")
        return cls(
            asked=asked[-_MAX_LIST:],
            weak_points=weak[-_MAX_LIST:],
            findings=findings[-_MAX_LIST:],
            notes=notes[-_MAX_LIST:],
            pending_quiz=_clip(quiz, 240),
        )

    def to_state_patch(self) -> dict[str, Any]:
        """写回 agent_state 的补丁（不覆盖无关键）。"""
        patch: dict[str, Any] = {
            "asked_questions": list(self.asked),
            "weak_points": list(self.weak_points),
            "memory_notes": list(self.notes),
        }
        if self.pending_quiz:
            patch["pending_quiz"] = self.pending_quiz
        return patch

    def remember(self, kind: str, text: str) -> None:
        if kind == "asked":
            _bounded_append(self.asked, text)
        elif kind == "weak":
            _bounded_append(self.weak_points, text)
        elif kind == "finding":
            _bounded_append(self.findings, text)
        elif kind == "quiz":
            self.pending_quiz = _clip(text, 240)
        else:
            _bounded_append(self.notes, text)

    def absorb_omitted(self, omitted: list[dict[str, Any]], *, limit: int = 12) -> None:
        """把被压缩掉的对话压成短笔记，避免「只记得条数」。"""
        lines: list[str] = []
        for m in omitted:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            content = m.get("content")
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("text"):
                        texts.append(str(item["text"]))
                content = " ".join(texts)
            snippet = _clip(str(content or ""), 80)
            if snippet:
                lines.append(f"{role}:{snippet}")
            if len(lines) >= limit:
                break
        if lines:
            _bounded_append(self.notes, "早期对话摘要：" + " | ".join(lines), limit=_MAX_LIST)

    def render(self) -> str:
        """模型可见的记忆段落（不含 marker）。"""
        parts: list[str] = []
        if self.asked:
            parts.append("已覆盖：" + "；".join(self.asked[-8:]))
        if self.weak_points:
            parts.append("薄弱点：" + "；".join(self.weak_points[-8:]))
        if self.findings:
            parts.append("核验：" + "；".join(self.findings[-5:]))
        if self.pending_quiz:
            parts.append("待点评练习：" + self.pending_quiz)
        if self.notes:
            parts.append("笔记：" + "；".join(self.notes[-6:]))
        return "\n".join(parts)

    def dump_block(self) -> str:
        """可持久化的 system 段：JSON 状态 + 给模型看的短文。"""
        payload = json.dumps(self.to_state_patch(), ensure_ascii=False)
        rendered = self.render()
        body = payload if not rendered else f"{payload}\n{rendered}"
        return f"{MEMORY_MARKER}\n{body}"

    @classmethod
    def load_from_messages(cls, messages: list[dict[str, Any]]) -> WorkingMemory:
        for m in reversed(messages):
            if m.get("role") != "system":
                continue
            content = m.get("content")
            if not isinstance(content, str) or not content.startswith(MEMORY_MARKER):
                continue
            rest = content[len(MEMORY_MARKER):].lstrip("\n")
            first, _, _tail = rest.partition("\n")
            try:
                return cls.from_state(json.loads(first))
            except (json.JSONDecodeError, TypeError, ValueError):
                return cls()
        return cls()
