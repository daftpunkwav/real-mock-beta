"""会话提示词构建（mixin）：档案查询、公司上下文、结构化记忆段落。

从 :class:`interview_service.services.interview.session_state.InterviewSessionState`
拆出，职责单一：构造 system prompt 及其每回合刷新的记忆段落。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal, cast

from sqlalchemy.orm import Session

from shared.database import api_db_session
from shared.services.candidate_read import get_candidate_profile, get_user_profile
from interview_service.schemas import InterviewConfig
from shared.catalogs.company import get_company_context
from shared.capabilities.ai.agent import WorkingMemory
from interview_service.services.interview.agent_prompts import build_system_prompt

if TYPE_CHECKING:
    from interview_service.services.interview.session_state import InterviewSessionState

logger = logging.getLogger(__name__)


class SessionPromptMixin:
    """system prompt 构建；依赖宿主状态机的 session / agent_state / workflow 字段。"""

    session: Any

    if TYPE_CHECKING:
        _self: InterviewSessionState

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

    def get_user_profile(self, db: Session):
        with api_db_session() as api_db:
            return get_user_profile(api_db, self.session.profile_id)

    def get_candidate(self, db: Session):
        with api_db_session() as api_db:
            return get_candidate_profile(api_db, self.session.resume_id)

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


__all__ = ["SessionPromptMixin"]
