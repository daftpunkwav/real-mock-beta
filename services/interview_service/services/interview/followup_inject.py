"""追问信号 + RAG 命中注入与消息尾部整理。

从 :mod:`interview_service.services.interview.runner` 拆出，职责单一：
- 追问信号分析（needs_followup）注入 system 消息并记录薄弱点；
- RAG 命中注入 system 消息；
- 整理消息尾部：保证 user 消息在末尾、本轮追加的 system 提示在 user 之后。
"""

from __future__ import annotations

import logging
from typing import Any

from interview_service.services.interview.session_state import InterviewSessionState
from interview_service.services.interview.followup import analyze as analyze_followup

logger = logging.getLogger(__name__)


def append_followup_and_rag(
    state: InterviewSessionState,
    *,
    user_text: str,
    last_question: str,
    tech_domains: list[str],
    phase_id: str,
    rag_msg: dict[str, Any] | None,
    face: dict[str, Any] | None,
    build_user_content: Any,
    session_id: int,
) -> None:
    """追问信号注入 + RAG 命中注入 + 整理消息尾部（保持 user 在末尾）。

    追问引导与 RAG 系统消息按追加顺序暂存，替换完 user 消息后原序放回，
    保证 user 之后只跟本轮追加的 system 提示。
    """
    signal = analyze_followup(
        user_text,
        question=last_question,
        tech_domains=tech_domains,
        phase_id=phase_id,
    )
    if signal.needs_followup:
        state.messages.append({
            "role": "system",
            "content": f"[追问引导：{signal.category}] {signal.suggested_probe}",
        })
        state.note_weak_point(f"[{signal.category}] {signal.suggested_probe}")
        clues = state.agent_state.setdefault("followup_clues", [])
        clues.append(signal.category)
        if len(clues) > 60:
            del clues[:-60]
        logger.info(
            "追问信号: session=%s cat=%s len=%d",
            session_id, signal.category, len(user_text),
        )

    state.refresh_system_memory()

    if rag_msg:
        state.messages.append(rag_msg)

    # 追问引导与 RAG 追加在 user 之后,先 pop 再替换 user,最后追加回
    trailing_msgs: list[dict[str, Any]] = []
    for _ in range(5):
        if not state.messages:
            break
        tail = state.messages[-1]
        if tail.get("role") != "system":
            break
        content = tail.get("content", "")
        if not (isinstance(content, str) and (
            content.startswith("[追问引导") or content.startswith("## 企业知识库")
        )):
            break
        trailing_msgs.append(state.messages.pop())
    trailing_msgs.reverse()

    user_content = build_user_content(user_text, face)
    state.messages[-1] = {"role": "user", "content": user_content}
    for m in trailing_msgs:
        state.messages.append(m)


__all__ = ["append_followup_and_rag"]
