"""面试报告 API。

- 流式端点 ``/{session_id}/stream``：单次 LLM 结构化生成报告，再将 JSON
  伪流式分片推送，最后 ``done`` 附完整 report（避免 stream + chat_json 双次计费）；
- 异常时仅返回脱敏后的提示文案，上游异常细节走 logger.exception；
- 状态比较统一使用 :class:`shared.core.constants.SessionStatus` 枚举值，
  防止字符串漂移。
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from shared.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, SessionStatus
from shared.core.errors import raise_error
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep
from shared.core.security import redact_api_key
from shared.core.session_auth import assert_session_token, extract_token
from shared.database import get_db
from interview_service.models import GrowthRecord, InterviewSession
from interview_service.schemas import InterviewReport, InterviewReportResponse
from interview_service.services.interview.report import generate_and_persist_report
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)
router = APIRouter()

# SSE done/error 事件的常量文案（避免上游异常泄露）
_SSE_ERR_GENERIC = "报告生成失败，请稍后重试"
# 伪流式分片大小（字符），兼顾首包延迟与事件数量
_PSEUDO_STREAM_CHUNK = 48


def _safe_json_list(raw: str | None, *, field: str, record_id: int) -> list:
    """解析成长记录 JSON 列表；坏数据降级为 []，避免整列表 500。"""
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


@router.get("/growth/history", dependencies=[Depends(require_local_peer)])
def get_growth_history(db: Session = Depends(get_db)):
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


@router.get("/growth/system-insights", dependencies=[Depends(require_local_peer)])
def get_system_growth_insights():
    """系统级自我成长洞察（跨面试聚合，非候选人个人隐私外泄）。"""
    from interview_service.services.growth.learning import get_system_insights

    return get_system_insights(limit=15)


@router.get(
    "/{session_id}/stream",
    dependencies=[
        Depends(require_local_peer),
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def get_report_stream(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
    """流式返回报告（单次 LLM；与 finish 共用 persist 语义）。

    - 已有 report 则短路，不重复调用 LLM；
    - 否则 ``generate_and_persist_report``（含 GrowthRecord）一次完成；
    - JSON 伪流式分片推送 + ``done`` 携带同一份结构。
    """
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status != SessionStatus.COMPLETED.value:
        raise_error("A2003")

    llm = LLMClient.from_db(db)

    async def event_stream():
        try:
            # 已有正式报告：短路，避免重复 LLM / 双写 GrowthRecord
            if session.report and session.report != "{}":
                report_json = session.report
                report_payload = json.loads(report_json)
            else:
                report = await generate_and_persist_report(session, llm, db)
                report_json = report.model_dump_json()
                report_payload = json.loads(report_json)
            # 伪流式：同一份 JSON 分片推送，便于前端渐进展示
            for i in range(0, len(report_json), _PSEUDO_STREAM_CHUNK):
                chunk = report_json[i : i + _PSEUDO_STREAM_CHUNK]
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'report': report_payload}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            # 客户端断开：记录但不再尝试 yield（连接已关闭）
            logger.info("SSE 客户端断开 sid=%s", session_id)
            raise
        except Exception as e:
            # 仅返回脱敏后的错误文案，原始异常走 logger.exception
            # 防止上游错误信息中可能含 API Key 等敏感字段
            safe_detail = redact_api_key(str(e)) or _SSE_ERR_GENERIC
            logger.exception("流式报告失败 sid=%s: %s", session_id, safe_detail)
            yield f"data: {json.dumps({'type': 'error', 'message': _SSE_ERR_GENERIC, 'code': 'C1001', 'retryable': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{session_id}",
    response_model=InterviewReportResponse,
    dependencies=[Depends(require_local_peer)],
)
def get_report(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)

    if not session.report or session.report == "{}":
        raise_error("A2004")

    report = InterviewReport(**json.loads(session.report))
    messages = json.loads(session.messages or "[]")

    duration = None
    if session.started_at and session.ended_at:
        delta = session.ended_at - session.started_at
        duration = round(delta.total_seconds() / 60, 1)

    return InterviewReportResponse(
        session_id=session_id,
        report=report,
        messages_count=len([m for m in messages if m["role"] in ("user", "assistant")]),
        duration_minutes=duration,
    )
