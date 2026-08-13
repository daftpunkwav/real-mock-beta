"""报告后台生成调度（WS mixin）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from shared.core.constants import SessionStatus
from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.services.interview.agent import generate_and_persist_report

logger = logging.getLogger(__name__)


class ReportSchedulerMixin:
    """依赖宿主提供 session_id / llm / send / _report_task / _spawn。"""

    if TYPE_CHECKING:
        # 宿主字段契约（mypy 可见，运行时跳过）：由 InterviewWSHandler.__init__ 注入
        session_id: int
        llm: Any
        _report_task: Any

        async def send(self, msg_type: str, **payload: Any) -> None: ...
        def _spawn(self, coro) -> Any: ...

    def _schedule_report_generation(self) -> None:
        """后台生成报告（独立 DB session），避免阻塞 WS / 重复任务。"""
        if self._report_task is not None and not self._report_task.done():
            return
        if self.llm is None:
            return
        self._report_task = self._spawn(self._generate_report_bg())

    async def _generate_report_bg(self) -> None:
        if self.llm is None:
            return
        db = SessionLocal()
        try:
            session = (
                db.query(InterviewSession)
                .filter(InterviewSession.id == self.session_id)
                .first()
            )
            if not session:
                return
            # 已有报告则跳过
            raw = (session.report or "").strip()
            if session.status == SessionStatus.COMPLETED.value and raw and raw != "{}":
                try:
                    await self.send(
                        "interview_complete",
                        session_id=self.session_id,
                        overall_score=session.overall_score,
                    )
                except Exception:
                    pass
                return
            await generate_and_persist_report(session, self.llm, db)
            try:
                await self.send(
                    "interview_complete",
                    session_id=self.session_id,
                    overall_score=session.overall_score,
                )
            except Exception:
                pass
        except Exception as e:
            logger.exception(
                "后台报告生成失败 sid=%s: %s", self.session_id, e
            )
            try:
                await self.send(
                    "error",
                    message="口头收尾已完成，但报告生成失败，请稍后在报告页重试",
                    code="C1001",
                    retryable=True,
                )
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # runner 事件 → 前端 WS 事件（仅非流式路径保留；主流式走 _stream_events_with_tts）
    # ------------------------------------------------------------------
