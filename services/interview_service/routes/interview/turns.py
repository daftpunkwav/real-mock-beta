"""面试回合：start / message / finish 与 Runner 事件流消费。

这些 handler 挂到 ``interview`` 主路由（见 ``interview.py`` 的组装）；
``start_interview`` / ``send_message`` 的源码必须保留
``InterviewRunner`` / ``phases_remaining()`` 字样（会话修复测试用
``inspect.getsource`` 校验，禁止回到 ``agent.start`` / ``agent.respond``）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from shared.core.constants import SessionStatus
from shared.core.errors import ApiBusinessError, raise_error
from shared.core.session_auth import assert_session_token, extract_token
from shared.database import get_sessions_db
from interview_service.ai import session_llm
from interview_service.models import InterviewSession
from interview_service.schemas import ChatMessage, FinishInterviewResponse, InterviewMessageRequest, InterviewMessageResponse
from interview_service.services.interview.events import EventKind
from interview_service.services.interview.report import generate_and_persist_report
from interview_service.services.interview.runner import InterviewRunner
from interview_service.services.interview.session_state import InterviewSessionState

logger = logging.getLogger(__name__)


async def _collect_turn_result(stream) -> tuple[str, bool]:
    """消费 Runner 事件流，返回 (最终文案, is_complete)。

    错误处理：runner 通过 StreamEvent.error_code 携带业务码（A2002 / C0001 等），
    REST 路径选择与 WS 路径一致的错误码；具体原因仅记日志（避免上游异常细节
    泄漏到 envelope）。若 error_code 缺失，按 C0001 兜底（runner 实现侧的契约）。
    """
    content = ""
    is_complete = False
    error_code: str = ""
    error_message: str = ""
    async for event in stream:
        if event.kind == EventKind.TOKEN:
            content += event.token
        elif event.kind == EventKind.TURN_COMPLETE:
            content = event.content
            is_complete = bool(event.is_complete)
        elif event.kind == EventKind.ERROR:
            error_code = event.error_code or "C0001"
            error_message = event.error or "面试执行失败"
    if error_code:
        # 仅日志保留原始 message；envelope 用目录标准文案 + hint
        logger.warning("Runner 返回错误: code=%s msg=%s", error_code, error_message)
        from shared.core.errors import get_spec

        spec = get_spec(error_code)
        raise ApiBusinessError(
            spec,
            message=spec.message,
        ) from None
    return content, is_complete


async def start_interview(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status not in (SessionStatus.PENDING.value, SessionStatus.ACTIVE.value):
        raise_error("A2002")

    llm = session_llm(db, session)
    if not llm.api_key:
        raise_error("A0006")

    agent = InterviewSessionState(session, llm)
    runner = InterviewRunner(session, llm, agent)
    opening, _ = await _collect_turn_result(runner.stream_opening(db))

    return {
        "session_id": session_id,
        "message": ChatMessage(role="assistant", content=opening, timestamp=datetime.now(timezone.utc)),
        "current_phase": session.current_phase,
    }


async def send_message(
    session_id: int,
    body: InterviewMessageRequest,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status == SessionStatus.COMPLETED.value:
        raise_error("A2002")

    llm = session_llm(db, session)
    if not llm.api_key:
        raise_error("A0006")

    agent = InterviewSessionState(session, llm)
    runner = InterviewRunner(session, llm, agent)
    reply, is_complete = await _collect_turn_result(
        runner.stream_turn(
            body.content,
            db,
            face=body.face_analysis,
            image_b64=body.image_base64,
        )
    )

    if is_complete:
        try:
            report = await generate_and_persist_report(session, llm, db)
        except Exception as e:
            # 对外通用文案，细节仅日志（防上游异常泄漏）
            logger.exception("报告生成失败 sid=%s", session_id)
            raise_error("C1001", cause=e)

    return InterviewMessageResponse(
        session_id=session_id,
        message=ChatMessage(role="assistant", content=reply, timestamp=datetime.now(timezone.utc)),
        current_phase=session.current_phase,
        is_complete=is_complete,
        # phases_remaining 是方法，必须调用
        phases_remaining=list(agent.phases_remaining()) if not is_complete else [],
    )


async def finish_interview(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
) -> FinishInterviewResponse:
    """提前结束面试并生成报告。

    若 WS 已落库报告则直接返回；否则触发一次生成（与 WS 后台共用锁防双打）。
    """
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if (
        session.status == SessionStatus.COMPLETED.value
        and session.report
        and session.report != "{}"
    ):
        return FinishInterviewResponse(session_id=session_id, status="already_completed")

    # 口头收尾可能已把 status 标 completed 但 report 仍空：补生成
    llm = session_llm(db, session)
    try:
        await generate_and_persist_report(session, llm, db)
    except Exception as e:
        logger.exception("报告生成失败 sid=%s", session_id)
        raise_error("C1001", cause=e)
    return FinishInterviewResponse(
        session_id=session_id,
        status=SessionStatus.COMPLETED.value,
        overall_score=session.overall_score,
    )
