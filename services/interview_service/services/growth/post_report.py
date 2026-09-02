"""报告落库后的成长域编排（GrowthRecord + 系统学习）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.schemas import InterviewReport
from interview_service.services.growth.persist_record import persist_growth_record

logger = logging.getLogger(__name__)


def notify_report_persisted(
    session: InterviewSession,
    *,
    report: dict[str, Any] | None = None,
) -> None:
    """系统学习 JSON 沉淀；失败仅记 debug。"""
    try:
        from interview_service.services.growth.learning import record_interview_learning

        record_interview_learning(session, report=report)
    except Exception:
        logger.debug("报告落库后成长学习记录失败 sid=%s", session.id, exc_info=True)


def complete_interview_side_effects(
    db: Session,
    session: InterviewSession,
    report: InterviewReport,
) -> None:
    """报告 session 已提交后：GrowthRecord + 系统学习。"""
    try:
        persist_growth_record(db, session, report)
    except Exception:
        logger.debug("GrowthRecord 落库失败 sid=%s（报告已保留）", session.id, exc_info=True)
        return
    notify_report_persisted(session, report=report.model_dump())
