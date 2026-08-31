"""面试 Agent 数据层：消息历史、阶段索引、状态持久化。

提示词见 :mod:`agent_prompts`；文本过滤见 :mod:`agent_text`；报告见 :mod:`report`。
本模块 re-export 旧符号以保持 import 兼容。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from shared.models import Resume, UserProfile
from interview_service.models import InterviewSession
from shared.schemas import CandidateProfile
from interview_service.schemas import InterviewConfig
from shared.catalogs.company import get_company_context
from interview_service.services.interview.agent_prompts import build_system_prompt
from interview_service.services.interview.turn_output import TurnOutput
from interview_service.services.interview.agent_text import (
    INTERVIEW_COMPLETE_MARKER,
    PHASE_COMPLETE_MARKER,
    ThinkStreamFilter,
    detect_emotion,
    has_marker,
    strip_markers,
    strip_think_blocks,
)
from interview_service.services.interview.report import (
    generate_and_persist_report,
    generate_report,
    stream_report,
)
from interview_service.services.interview.workflows import (
    InterviewPhase,
    get_workflow,
)
from shared.capabilities.ai.agent import WorkingMemory
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

class InterviewAgent:
    """面试 Agent 数据层：消息历史、阶段索引、状态持久化。"""

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

    # ---- 配置/上下文查询（只读） --------------------------------------------

    def get_config(self) -> InterviewConfig:
        # DB 字段是自由 str，运行时可能含旧值；cast 到 Literal 交由 Pydantic 校验
        return InterviewConfig(
            role=self.session.role,
            level=self.session.level,
            company=self.session.company,
            workflow_type=cast(
                Literal["technical", "hr", "management"],
                self.session.workflow_type or "technical",
            ),
            personality=cast(
                Literal["gentle", "professional", "pressure", "hr", "expert"],
                self.session.personality or "professional",
            ),
            strictness=self.session.strictness,
            interview_style=cast(
                Literal["guided", "deep_dive", "continuous", "challenging"],
                self.session.interview_style or "deep_dive",
            ),
            resume_id=self.session.resume_id,
        )

    def get_user_profile(self, db: Session) -> UserProfile | None:
        return db.query(UserProfile).filter(UserProfile.id == self.session.profile_id).first()

    def get_candidate(self, db: Session) -> CandidateProfile | None:
        if not self.session.resume_id:
            return None
        resume = db.query(Resume).filter(Resume.id == self.session.resume_id).first()
        if not resume:
            return None
        try:
            return CandidateProfile(**json.loads(resume.parsed_profile))
        except (json.JSONDecodeError, Exception):
            return None

    def _system_learning_section(self) -> str:
        """从跨面试积累的系统学习数据中提取供本场面试参考的摘要。

        实现 PRD 4.7「自我成长」的反哺闭环：将历史面试中该公司/岗位的
        常见弱项、有效追问线索注入 system prompt，让 Agent 自发参考。
        读取失败或无数据时返回空串，不影响主流程。
        """
        try:
            from interview_service.services.growth.learning import get_system_insights

            insights = get_system_insights(limit=5)
        except Exception as e:
            logger.warning("读取系统学习洞察失败: %s", e)
            return ""

        parts: list[str] = []
        company = self.session.company or ""
        role = self.session.role or ""

        # 该公司历史均分（低分提示 Agent 加大考察力度）
        avg_scores = insights.get("avg_scores_by_company") or {}
        company_avg = avg_scores.get(company)
        if isinstance(company_avg, (int, float)) and company_avg < 80:
            parts.append(
                f"目标公司「{company}」历史面试均分 {company_avg}，"
                "建议适度加大项目深挖与技术追问力度。"
            )

        # 近期有效追问线索（薄弱点），按公司/岗位相关性优先
        probes = insights.get("recent_probes") or []
        relevant: list[str] = []
        for p in probes:
            if not isinstance(p, dict):
                continue
            p_company = p.get("company") or ""
            p_role = p.get("role") or ""
            # 同公司或同岗位的线索优先，否则取通用线索
            if p_company == company or p_role == role or not relevant:
                relevant.append(str(p.get("point", ""))[:120])
            if len(relevant) >= 3:
                break
        if relevant:
            parts.append(
                "近期面试中发现的常见薄弱点（可针对性考察）：\n- "
                + "\n- ".join(relevant)
            )

        if not parts:
            return ""
        return "\n\n## 系统学习摘要（跨面试积累，供参考）\n" + "\n".join(parts)

    def _memory_section(self) -> str:
        """结构化记忆摘要（压缩后仍可用）。"""
        text = WorkingMemory.from_state(self.agent_state).render()
        if not text:
            return ""
        return "\n\n## 会话结构化记忆（请勿重复已问问题）\n" + text

    def build_opening_prompt(self, db: Session) -> str:
        """构建首回合系统提示。"""
        config = self.get_config()
        candidate = self.get_candidate(db)
        profile = self.get_user_profile(db)
        company_ctx = get_company_context(config.company)
        phase = self.current_phase()
        prompt = build_system_prompt(
            config, candidate, company_ctx, self.workflow, phase, profile
        )
        # 系统学习摘要（跨面试积累，整场不变）+ 会话结构化记忆（每回合刷新）
        return prompt + self._system_learning_section() + self._memory_section()

    def refresh_system_memory(self) -> None:
        """刷新 system prompt 头部中的结构化记忆段落。

        每回合调用，使 asked_questions / weak_points / github_findings 的最新值
        反映到 system prompt，避免长会话压缩后重复提问、遗漏薄弱点追踪。

        仅替换 ``messages[0]`` 的 system content 中的记忆段落，不重建整个 prompt，
        避免每回合重跑 DB 查询（候选人档案/公司知识仅在开场构建一次）。
        """
        if not self.messages or self.messages[0].get("role") != "system":
            return
        content = self.messages[0].get("content", "")
        if not isinstance(content, str):
            return
        # 移除旧的记忆段落（含其前的空行），再追加最新值
        marker = "## 会话结构化记忆（请勿重复已问问题）"
        if marker in content:
            content = content.split(marker)[0].rstrip()
        memory = self._memory_section()
        if memory:
            self.messages[0]["content"] = content + "\n\n" + memory

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


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------



__all__ = [
    "InterviewAgent",
    "build_system_prompt",
    "ThinkStreamFilter",
    "detect_emotion",
    "has_marker",
    "strip_markers",
    "strip_think_blocks",
    "PHASE_COMPLETE_MARKER",
    "INTERVIEW_COMPLETE_MARKER",
    "generate_and_persist_report",
    "generate_report",
    "stream_report",
]
