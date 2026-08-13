"""参考提纲服务（WS mixin）。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.services.interview.agent import strip_markers, strip_think_blocks

logger = logging.getLogger(__name__)


class HintServiceMixin:
    """依赖宿主提供 session_id / llm / agent / send / _hint_inflight。"""

    _HINT_TIMEOUT_SEC: float = 20.0
    _HINT_CTX_CHARS: int = 1200

    if TYPE_CHECKING:
        # 宿主字段契约（mypy 可见，运行时跳过）：由 InterviewWSHandler.__init__ 注入
        session_id: int
        llm: Any
        agent: Any
        _hint_inflight: str | None

        async def send(self, msg_type: str, **payload: Any) -> None: ...

    async def _on_request_hint(self, data: dict[str, Any]) -> None:
        """使用独立 DB session，避免与主回合 ORM Session 竞态。"""
        question = strip_think_blocks((data.get("question") or "").strip())
        question = strip_markers(question)
        question = self._extract_hint_question(question)
        if not question or not self.llm:
            await self.send(
                "reference_hint",
                question=question or "",
                content="暂时无法生成参考回答，请根据你的实际经历组织语言。",
            )
            return
        key = question[:200]
        if self._hint_inflight == key:
            return
        self._hint_inflight = key
        hint_db = SessionLocal()
        try:
            await self.send("reference_hint_loading", question=question)
            session = (
                hint_db.query(InterviewSession)
                .filter(InterviewSession.id == self.session_id)
                .first()
            )
            try:
                hint = await asyncio.wait_for(
                    self._generate_reference_hint(question, hint_db, session),
                    timeout=self._HINT_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning("参考提纲超时 sid=%s", self.session_id)
                hint = "生成超时。可先按 STAR 结构自拟要点：情境 → 任务 → 行动 → 结果（尽量带量化）。"
            except Exception as e:
                logger.warning("参考提纲异常 sid=%s: %s", self.session_id, e)
                hint = "暂时无法生成参考回答，请根据你的实际经历组织语言。"
            hint = strip_markers(strip_think_blocks(hint or ""))
            if not hint.strip():
                hint = "暂时无法生成参考回答，请根据你的实际经历组织语言。"
            await self.send("reference_hint", question=question, content=hint)
        finally:
            if self._hint_inflight == key:
                self._hint_inflight = None
            try:
                hint_db.close()
            except Exception:
                pass

    @staticmethod
    def _extract_hint_question(text: str) -> str:
        """从面试官整段回复中提取末尾提问，控制二次 LLM 输入体积。"""
        t = (text or "").strip()
        if not t:
            return ""
        parts = [p.strip() for p in t.split("\n") if p.strip()]
        if not parts:
            return t[:500]
        for line in reversed(parts):
            if any(q in line for q in ("?", "？", "吗", "呢", "请", "介绍", "聊聊", "说说")):
                return line[:500]
        return parts[-1][:500]

    async def _generate_reference_hint(
        self, question: str, db: Session, session: InterviewSession | None
    ) -> str:
        assert self.llm and self.agent
        _ = db, session  # 预留：可按 session 拉简历片段；当前用 agent.messages
        system_ctx = ""
        for m in self.agent.messages:
            if m.get("role") == "system":
                system_ctx = str(m.get("content", ""))[: self._HINT_CTX_CHARS]
                break
        from shared.core.prompts import with_agent_output_rules

        messages = [
            {
                "role": "system",
                "content": with_agent_output_rules(
                    "你是面试辅导助手。根据候选人背景，为面试官的问题生成简洁参考回答提纲。\n"
                    "要求：3-5 个要点，每点一行，以「•」开头；结合简历具体经历；不要冗长；"
                    "不要替候选人捏造未提及的项目细节；不要输出思考过程或 <think> 标签。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"候选人背景摘要：\n{system_ctx or '（暂无详细档案）'}\n\n"
                    f"面试官问题：{question}\n\n请给出参考回答提纲："
                ),
            },
        ]
        try:
            return await self.llm.chat(messages, temperature=0.4, max_tokens=400)
        except Exception as e:
            logger.warning("参考提纲生成失败: %s", e)
            return "暂时无法生成参考回答，请根据你的实际经历组织语言。"

    # ------------------------------------------------------------------
    # 静默追问
    # ------------------------------------------------------------------
