"""成长域 HTTP API（与报告路由分离）。"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.core.local_only import require_local_peer
from shared.database import get_sessions_db
from interview_service.models import GrowthRecord

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_json_list(raw: str | None, *, field: str, record_id: int) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "GrowthRecord.%s 解析失败 id=%s，已降级为空列表", field, record_id
        )
        return []


@router.get("/history", dependencies=[Depends(require_local_peer)])
def get_growth_history(db: Session = Depends(get_sessions_db)):
    records = db.query(GrowthRecord).order_by(GrowthRecord.created_at.desc()).limit(20).all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "weak_skills": _safe_json_list(r.weak_skills, field="weak_skills", record_id=r.id),
            "training_plan": _safe_json_list(
                r.training_plan, field="training_plan", record_id=r.id
            ),
            "created_at": r.created_at,
        }
        for r in records
    ]


@router.get("/system-insights", dependencies=[Depends(require_local_peer)])
def get_system_growth_insights():
    """系统级自我成长洞察（跨面试聚合）。"""
    from interview_service.services.growth.learning import get_system_insights

    return get_system_insights(limit=15)
