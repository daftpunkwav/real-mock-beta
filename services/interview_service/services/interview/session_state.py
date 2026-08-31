"""面试会话状态机（InterviewSessionState）。

职责：
- 消息历史 / 阶段索引 / 结构化状态（agent_state）的加载与持久化；
- 阶段推进、回合控制信息落盘；
- system prompt 构建见 :mod:`session_prompt`（SessionPromptMixin）。

提示词见 :mod:`agent_prompts`；文本过滤见 :mod:`agent_text`；报告见 :mod:`report`。
企业目录：跨会话公司知识来自 :mod:`shared.catalogs.company`，本模块只读引用。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from shared.catalogs.company import get_company_context
from interview_service.services.interview.session_prompt import SessionPromptMixin
from interview_service.services.interview.turn_output import TurnOutput
from interview_service.services.interview.agent_text import (
    PHASE_COMPLETE_MARKER,
    has_marker,
    strip_markers,
)
from interview_service.services.interview.workflows import (
    InterviewPhase,
    get_workflow,
)
from shared.capabilities.ai.llm.client import LLMClient


class InterviewSessionState(SessionPromptMixin):
    """面试会话状态机：消息历史、阶段索引、状态持久化、提示词构建。"""

    def __init__(self, session: InterviewSession, llm: LLMClient):
        self.session = session
        self.llm = llm
        self._load_state()

    # ---- 状态加载/保存 -----------------------------------------------------

    def _load_state(self) -> None:
        try:
            self.agent_state: dict[str, Any] = json.loads(self.session.agent_state or "{}")
        except json.JSONDecodeError:
            self.agent_state = {}

        try:
            self.messages: list[dict[str, Any]] = json.loads(self.session.messages or "[]")
        except json.JSONDecodeError:
            self.messages = []

        self.workflow = get_workflow(self.session.workflow_type)
        # 夹紧到合法范围，防止已废弃或被截短的 workflow 导致越界
        _raw_idx = self.agent_state.get("phase_idx", 0)
        _max_idx = max(0, len(self.workflow.phases) - 1)
        self.current_phase_idx: int = max(0, min(_raw_idx, _max_idx))
        self.questions_in_phase: int = self.agent_state.get("questions_in_phase", 0)
        self.asked_topics: list[str] = self.agent_state.get("asked_topics", [])
        # 长上下文结构化记忆（40 分钟面试用）
        self.agent_state.setdefault("weak_points", [])
        self.agent_state.setdefault("followup_clues", [])
        self.agent_state.setdefault("github_findings", [])
        self.agent_state.setdefault("tool_trace", [])
        self.agent_state.setdefault("asked_questions", [])

    def save_state(self, db: Session) -> None:
        """将当前状态写回数据库。"""
        self.agent_state.update({
            "phase_idx": self.current_phase_idx,
            "questions_in_phase": self.questions_in_phase,
            "asked_topics": self.asked_topics,
        })
        self.session.agent_state = json.dumps(self.agent_state, ensure_ascii=False)
        self.session.messages = json.dumps(self.messages, ensure_ascii=False)
        self.session.current_phase = self.current_phase().id
        db.commit()

    def note_question(self, question_text: str) -> None:
        """记录已问问题（结构化，便于压缩后仍可去重）。"""
        q = (question_text or "").strip()
        if not q:
            return
        asked = self.agent_state.setdefault("asked_questions", [])
        # 只保留摘要前 120 字
        snippet = q[:120]
        if snippet not in asked:
            asked.append(snippet)
        if len(asked) > 80:
            del asked[:-80]

    def note_weak_point(self, point: str) -> None:
        """记录候选人薄弱点线索。"""
        p = (point or "").strip()
        if not p:
            return
        weak = self.agent_state.setdefault("weak_points", [])
        if p not in weak:
            weak.append(p[:200])
        if len(weak) > 30:
            del weak[:-30]

    def note_turn_output(self, output: TurnOutput) -> None:
        """持久化回合控制信息：追问预案与即时简评（拟真追问/报告复用）。"""
        if output.probe:
            self.agent_state["last_probe"] = output.probe
        ts = output.turn_score
        if ts:
            self.agent_state["last_turn_score"] = {
                "brief": ts.brief,
                "rating": ts.rating,
                "weak_points": list(ts.weak_points),
            }
            for p in ts.weak_points:
                self.note_weak_point(p)

    # ---- 阶段查询 -----------------------------------------------------------

    def current_phase(self) -> InterviewPhase:
        if self.current_phase_idx < len(self.workflow.phases):
            return self.workflow.phases[self.current_phase_idx]
        return self.workflow.phases[-1]

    def phases_remaining(self) -> list[str]:
        return [p.name for p in self.workflow.phases[self.current_phase_idx:]]

    # ---- 状态推进 ----------------------------------------------------------

    def mark_active(self) -> None:
        """标记会话为进行中。"""
        self.session.status = "active"
        self.session.started_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """标记面试结束，并把阶段索引指向末尾。"""
        self.session.status = "completed"
        self.session.ended_at = datetime.now(timezone.utc)
        self.current_phase_idx = len(self.workflow.phases) - 1

    def record_user_text(self, content: str) -> None:
        """记录候选人发言到消息历史。"""
        self.messages.append({"role": "user", "content": content})

    def record_assistant_text(self, content: str) -> None:
        """记录面试官发言到消息历史，并写入结构化已问问题。"""
        self.messages.append({"role": "assistant", "content": content})
        # 控制标记剥离后记入 asked_questions
        clean = strip_markers(content)
        if clean:
            self.note_question(clean)

    def reset_messages(self) -> None:
        """重置消息历史（用于 start 时）。"""
        self.messages = []

    def set_questions_in_phase(self, value: int) -> None:
        self.questions_in_phase = value

    def advance_phase_if_needed(
        self, reply: str, *, phase_complete: bool | None = None
    ) -> bool:
        """根据 LLM 回复决定是否推进到下一阶段。

        ``phase_complete`` 来自回合协议控制区；None 时回落旧标记检测
        （兼容压缩前的历史消息）。

        Returns:
            bool: 是否发生阶段切换。
        """
        if phase_complete is None:
            phase_complete = has_marker(reply, PHASE_COMPLETE_MARKER)
        max_reached = self.questions_in_phase >= self.current_phase().max_questions
        if phase_complete or max_reached:
            # 防御：避免越界走到 workflow 末尾之后
            if self.current_phase_idx >= len(self.workflow.phases) - 1:
                self.questions_in_phase += 1
                return False
            self._advance_phase()
            return True
        self.questions_in_phase += 1
        return False

    def _advance_phase(self) -> None:
        self.current_phase_idx += 1
        self.questions_in_phase = 0
        if self.current_phase_idx < len(self.workflow.phases):
            phase = self.current_phase()
            content = self._phase_entry_message(phase)
            self.messages.append({
                "role": "system",
                "content": content,
            })

    def _phase_entry_message(self, phase: InterviewPhase) -> str:
        """构建进入新阶段时的 system message。

        反问环节（reverse_qa）使用专门的「公司代表角色」prompt，强调基于
        公司知识库回答候选人问题、未覆盖的坦诚说明；其他阶段用通用引导。
        """
        if phase.id == "reverse_qa":
            company_ctx = get_company_context(self.session.company or "")
            return (
                f"进入新阶段：{phase.name}（{phase.description}）。\n"
                f"{company_ctx}\n\n"
                "现在角色切换：你不再是考察者，而是该公司的代表（资深工程师/HR），"
                "回答候选人关于公司文化、团队、技术栈、业务方向、成长机会等问题。\n"
                "要求：\n"
                "1. 基于上方公司资料回答；资料未覆盖的内容应坦诚说明「这方面我没有确切信息」\n"
                "2. 回答专业、真实，避免空泛套话\n"
                "3. 仍可用 web_search_interview_exp 工具补充公开信息\n"
                "4. 回复禁止使用 emoji 表情"
            )
        return (
            f"进入新阶段：{phase.name}（{phase.description}）。"
            "请开始本阶段提问。回复禁止使用 emoji 表情。"
        )


__all__ = ["InterviewSessionState"]
