"""报告后台生成调度（WS mixin）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from shared.core.constants import SessionStatus
from shared.database import SessionLocal
from interview_service.models import InterviewSession
from interview_service.services.interview.report import generate_and_persist_report

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ReportSchedulerMixin:
    """报告后台生成。依赖 ctx.session_id / ctx.llm / ctx.report_task / send / _spawn。"""

    ctx: ConnectionContext

    def _schedule_report_generation(self) -> None:
        """后台生成报告（独立 DB session），避免阻塞 WS / 重复任务。"""
        if self.ctx.report_task is not None and not self.ctx.report_task.done():
            return
        if self.ctx.llm is None:
            return
        self.ctx.report_task = self._spawn(self._generate_report_bg())

    async def _generate_report_bg(self) -> None:
        if self.ctx.llm is None:
            return
        db = SessionLocal()
        try:
            session = (
                db.query(InterviewSession)
                .filter(InterviewSession.id == self.ctx.session_id)
                .first()
            )
            if not session:
                return
            raw = (session.report or "").strip()
            if session.status == SessionStatus.COMPLETED.value and raw and raw != "{}":
                try:
                    await self.send(
                        "interview_complete",
                        session_id=self.ctx.session_id,
                        overall_score=session.overall_score,
                    )
                except Exception:
                    logger.debug(
                        "报告已完成通知发送失败 sid=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                return
            await generate_and_persist_report(session, self.ctx.llm, db)
            try:
                await self.send(
                    "interview_complete",
                    session_id=self.ctx.session_id,
                    overall_score=session.overall_score,
                )
            except Exception:
                logger.debug(
                    "报告生成完成通知发送失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        except Exception as e:
            logger.exception(
                "后台报告生成失败 sid=%s: %s", self.ctx.session_id, e
            )
            try:
                await self.send(
                    "error",
                    message="口头收尾已完成，但报告生成失败，请稍后在报告页重试",
                    code="C1001",
                    retryable=True,
                )
            except Exception:
                logger.debug(
                    "报告失败 error 事件发送失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "报告后台 DB close 失败 sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
