"""面试报告生成与持久化。

锁 / 哨兵 CAS / GrowthRecord 同事务这一段对并发语义敏感，刻意不拆碎。
提示词与消息构造、评分辅助、流式生成分别拆到 report_prompt / report_score / report_stream。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.schemas import InterviewReport
from shared.capabilities.ai.llm.client import LLMClient
from interview_service.services.interview.report_prompt import build_report_messages
from interview_service.services.interview.report_score import (
    _apply_interrupt_politeness_penalty,
    _fallback_report,
)
from interview_service.services.interview.report_stream import stream_report

logger = logging.getLogger(__name__)

_REPORT_LOCKS: dict[int, asyncio.Lock] = {}

_REPORT_GENERATING_SENTINEL = '{"_generating":true}'


async def generate_report(
    session: InterviewSession,
    llm: LLMClient,
    face_records: list[dict] | None = None,
) -> InterviewReport:
    """根据面试对话生成评估报告。

    失败时向上抛出，避免调用方把假分数 ``_fallback_report`` 当作正式结果落库。
    仅在明确需要降级展示且不落库的场景再调用 :func:`_fallback_report`。
    """
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
) -> InterviewReport:
    """生成报告并写入 session / GrowthRecord（同一事务）。

    任意阶段失败整体回滚，避免「session 已 completed 但 GrowthRecord 缺失」。
    同 session 并发调用时加进程内锁 + DB 哨兵 CAS，避免 WS/HTTP / 多 worker 双打。
    """
    from sqlalchemy import or_, update

    from shared.core.constants import SessionStatus
    from interview_service.models import GrowthRecord

    sid = int(session.id)
    lock = _REPORT_LOCKS.setdefault(sid, asyncio.Lock())
    async with lock:
        try:
            db.refresh(session)
        except Exception:
            pass
        raw = (session.report or "").strip()
        if raw and raw != "{}" and raw != _REPORT_GENERATING_SENTINEL:
            try:
                return InterviewReport.model_validate_json(raw)
            except Exception:
                pass
        if raw == _REPORT_GENERATING_SENTINEL:
            # 另一路径正在生成：短暂等待后若已落库则返回
            for _ in range(30):
                await asyncio.sleep(0.2)
                try:
                    db.refresh(session)
                except Exception:
                    break
                cur = (session.report or "").strip()
                if cur and cur != _REPORT_GENERATING_SENTINEL and cur != "{}":
                    try:
                        return InterviewReport.model_validate_json(cur)
                    except Exception:
                        break
            # 超时仍卡在哨兵：清哨兵后由本路径重试
            try:
                db.execute(
                    update(InterviewSession)
                    .where(InterviewSession.id == sid)
                    .where(InterviewSession.report == _REPORT_GENERATING_SENTINEL)
                    .values(report="{}")
                )
                db.commit()
            except Exception:
                db.rollback()

        # DB CAS：仅当报告仍为空时写入哨兵
        claimed = False
        try:
            result = db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == sid)
                .where(
                    or_(
                        InterviewSession.report.is_(None),
                        InterviewSession.report == "",
                        InterviewSession.report == "{}",
                    )
                )
                .values(report=_REPORT_GENERATING_SENTINEL)
            )
            db.commit()
            # SQLAlchemy Result.rowcount 类型标注不完整，显式取 rowcount 防并发双写
            claimed = (getattr(result, "rowcount", 0) or 0) > 0
        except Exception:
            db.rollback()
            claimed = False

        if not claimed:
            try:
                db.refresh(session)
            except Exception:
                pass
            cur = (session.report or "").strip()
            if cur and cur != _REPORT_GENERATING_SENTINEL and cur != "{}":
                try:
                    return InterviewReport.model_validate_json(cur)
                except Exception:
                    pass
            # 可能刚被其他方设为哨兵：再等一轮
            if cur == _REPORT_GENERATING_SENTINEL:
                for _ in range(30):
                    await asyncio.sleep(0.2)
                    try:
                        db.refresh(session)
                    except Exception:
                        break
                    cur2 = (session.report or "").strip()
                    if cur2 and cur2 != _REPORT_GENERATING_SENTINEL and cur2 != "{}":
                        try:
                            return InterviewReport.model_validate_json(cur2)
                        except Exception:
                            break

        try:
            # 确保 ORM 对象与哨兵一致
            try:
                db.refresh(session)
            except Exception:
                pass
            report = await generate_report(session, llm, face_records)
            report = _apply_interrupt_politeness_penalty(session, report)

            growth = GrowthRecord(
                profile_id=session.profile_id,
                session_id=session.id,
                weak_skills=json.dumps(report.weaknesses, ensure_ascii=False),
                common_mistakes=json.dumps(report.weaknesses[:3], ensure_ascii=False),
                training_plan=json.dumps(report.training_plan, ensure_ascii=False),
            )

            try:
                session.report = report.model_dump_json()
                session.overall_score = report.overall_score
                session.status = SessionStatus.COMPLETED.value
                session.ended_at = datetime.now(timezone.utc)
                db.add(growth)
                db.commit()
                try:
                    from interview_service.services.growth.learning import record_interview_learning

                    record_interview_learning(session, report=report.model_dump())
                except Exception:
                    pass
            except Exception:
                db.rollback()
                raise
            return report
        except Exception:
            # 异常路径清哨兵，避免永久卡住
            try:
                db.execute(
                    update(InterviewSession)
                    .where(InterviewSession.id == sid)
                    .where(InterviewSession.report == _REPORT_GENERATING_SENTINEL)
                    .values(report="{}")
                )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
            raise
