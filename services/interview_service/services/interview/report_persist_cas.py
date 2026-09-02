"""报告生成哨兵 CAS 与并发等待（从 report 模块拆出）。"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.schemas import InterviewReport

logger = logging.getLogger(__name__)

REPORT_GENERATING_SENTINEL = '{"_generating":true}'

_REPORT_LOCKS: dict[int, asyncio.Lock] = {}


def lock_for_session(session_id: int) -> asyncio.Lock:
    return _REPORT_LOCKS.setdefault(session_id, asyncio.Lock())


def release_report_lock(session_id: int) -> None:
    """报告生成结束后释放进程内锁，避免长跑 dict 无界增长。"""
    _REPORT_LOCKS.pop(int(session_id), None)


async def wait_for_cached_report(db: Session, session: InterviewSession) -> InterviewReport | None:
    """若已有正式报告 JSON 则解析返回；哨兵则等待或清理。"""
    sid = int(session.id)
    raw = (session.report or "").strip()
    if raw and raw != "{}" and raw != REPORT_GENERATING_SENTINEL:
        try:
            return InterviewReport.model_validate_json(raw)
        except Exception:
            logger.debug("报告缓存 JSON 解析失败 sid=%s", sid, exc_info=True)
    if raw != REPORT_GENERATING_SENTINEL:
        return None

    for _ in range(30):
        await asyncio.sleep(0.2)
        try:
            db.refresh(session)
        except Exception:
            logger.debug("等待哨兵时 refresh session 失败 sid=%s", sid, exc_info=True)
            break
        cur = (session.report or "").strip()
        if cur and cur != REPORT_GENERATING_SENTINEL and cur != "{}":
            try:
                return InterviewReport.model_validate_json(cur)
            except Exception:
                logger.debug("等待哨兵后报告 JSON 解析失败 sid=%s", sid, exc_info=True)
                break

    try:
        db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == sid)
            .where(InterviewSession.report == REPORT_GENERATING_SENTINEL)
            .values(report="{}")
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("清报告生成哨兵失败 sid=%s", sid, exc_info=True)
    return None


def try_claim_report_generation(db: Session, session_id: int) -> bool:
    """CAS 抢占报告生成权；成功返回 True。"""
    try:
        result = db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .where(
                or_(
                    InterviewSession.report.is_(None),
                    InterviewSession.report == "",
                    InterviewSession.report == "{}",
                )
            )
            .values(report=REPORT_GENERATING_SENTINEL)
        )
        db.commit()
        return (getattr(result, "rowcount", 0) or 0) > 0
    except Exception:
        db.rollback()
        logger.debug("报告 CAS 抢占哨兵失败 sid=%s", session_id, exc_info=True)
        return False


async def wait_after_failed_claim(db: Session, session: InterviewSession) -> InterviewReport | None:
    """未抢到 CAS 时再等一轮，返回已落库报告或 None。"""
    sid = int(session.id)
    cur = (session.report or "").strip()
    try:
        db.refresh(session)
        cur = (session.report or "").strip()
    except Exception:
        logger.debug("未抢占路径 refresh session 失败 sid=%s", sid, exc_info=True)
        if cur and cur not in ("", "{}", REPORT_GENERATING_SENTINEL):
            try:
                return InterviewReport.model_validate_json(cur)
            except Exception:
                logger.debug("未抢占时报告 JSON 解析失败 sid=%s", sid, exc_info=True)

    if cur == REPORT_GENERATING_SENTINEL:
        for _ in range(30):
            await asyncio.sleep(0.2)
            try:
                db.refresh(session)
            except Exception:
                break
            cur2 = (session.report or "").strip()
            if cur2 and cur2 != REPORT_GENERATING_SENTINEL and cur2 != "{}":
                try:
                    return InterviewReport.model_validate_json(cur2)
                except Exception:
                    logger.debug("二次等待后报告 JSON 解析失败 sid=%s", sid, exc_info=True)
                    break
    return None


def clear_report_sentinel(db: Session, session_id: int) -> None:
    try:
        db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .where(InterviewSession.report == REPORT_GENERATING_SENTINEL)
            .values(report="{}")
        )
        db.commit()
    except Exception:
        logger.debug("报告异常路径清哨兵失败 sid=%s", session_id, exc_info=True)
        try:
            db.rollback()
        except Exception:
            logger.debug("报告异常路径 rollback 失败 sid=%s", session_id, exc_info=True)


def persist_session_report(
    db: Session,
    session: InterviewSession,
    report: InterviewReport,
) -> None:
    """仅写入 session 报告字段与完成状态（不含 GrowthRecord）。"""
    from datetime import datetime, timezone

    from shared.core.constants import SessionStatus

    session.report = report.model_dump_json()
    session.overall_score = report.overall_score
    session.status = SessionStatus.COMPLETED.value
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
