"""面试报告生成与 session 落库。

并发 CAS 见 ``report_persist_cas``；成长侧效应见 ``growth.post_report``。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.schemas import InterviewReport
from shared.capabilities.ai.llm.client import LLMClient
from interview_service.services.interview.report_prompt import build_report_messages
from interview_service.services.interview.report_score import (
    _apply_interrupt_politeness_penalty,
    _fallback_report,
)
from interview_service.services.interview.report_persist_cas import (
    clear_report_sentinel,
    lock_for_session,
    persist_session_report,
    release_report_lock,
    try_claim_report_generation,
    wait_after_failed_claim,
    wait_for_cached_report,
)
from interview_service.services.growth.post_report import complete_interview_side_effects

logger = logging.getLogger(__name__)


async def generate_report(
    session: InterviewSession,
    llm: LLMClient,
    face_records: list[dict] | None = None,
) -> InterviewReport:
    """根据面试对话生成评估报告；失败向上抛出。"""
    try:
        data = await llm.chat_json(build_report_messages(session, face_records))
        return InterviewReport(**data)
    except Exception as e:
        logger.error("报告生成失败: %s", e)
        raise


async def generate_and_persist_report(
    session: InterviewSession,
    llm: LLMClient,
    db: Session,
    face_records: list[dict] | None = None,
    *,
    run_growth_side_effects: bool = True,
) -> InterviewReport:
    """生成报告并写入 session；可选触发成长域副作用。"""
    sid = int(session.id)
    lock = lock_for_session(sid)
    try:
        async with lock:
            try:
                db.refresh(session)
            except Exception:
                logger.debug("报告生成前 refresh session 失败 sid=%s", sid, exc_info=True)

            cached = await wait_for_cached_report(db, session)
            if cached is not None:
                return cached

            claimed = try_claim_report_generation(db, sid)
            if not claimed:
                waited = await wait_after_failed_claim(db, session)
                if waited is not None:
                    return waited

            try:
                try:
                    db.refresh(session)
                except Exception:
                    logger.debug("生成前 refresh session 失败 sid=%s", sid, exc_info=True)
                report = await generate_report(session, llm, face_records)
                report = _apply_interrupt_politeness_penalty(session, report)
                persist_session_report(db, session, report)
                if run_growth_side_effects:
                    complete_interview_side_effects(db, session, report)
                return report
            except Exception:
                clear_report_sentinel(db, sid)
                raise
    finally:
        release_report_lock(sid)


__all__ = ["generate_report", "generate_and_persist_report", "_fallback_report"]
