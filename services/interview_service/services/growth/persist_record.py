"""成长记录落库（与报告生成模块解耦）。"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from interview_service.models import GrowthRecord, InterviewSession
from interview_service.schemas import InterviewReport

logger = logging.getLogger(__name__)


def persist_growth_record(
    db: Session,
    session: InterviewSession,
    report: InterviewReport,
) -> GrowthRecord:
    """根据报告写入 ``GrowthRecord``；与 session 报告分事务，失败不拖垮报告主路径。"""
    growth = GrowthRecord(
        profile_id=session.profile_id,
        session_id=session.id,
        weak_skills=json.dumps(report.weaknesses, ensure_ascii=False),
        common_mistakes=json.dumps(report.weaknesses[:3], ensure_ascii=False),
        training_plan=json.dumps(report.training_plan, ensure_ascii=False),
    )
    try:
        db.add(growth)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("GrowthRecord 落库失败 sid=%s", session.id)
        raise
    return growth
