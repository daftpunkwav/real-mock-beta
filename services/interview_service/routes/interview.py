"""面试会话 API。"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
    SessionStatus,
)
from shared.core.errors import ApiBusinessError, raise_error
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep
from shared.core.session_auth import (
    assert_session_token,
    cookie_should_be_secure,
    extract_token,
    new_access_token,
    set_session_cookie,
)
from shared.database import get_db
from interview_service.models import InterviewSession
from interview_service.schemas import (
    ChatMessage,
    InterviewConfig,
    InterviewMessageRequest,
    InterviewMessageResponse,
    InterviewSessionResponse,
    ResumePickerItem,
)
from shared.models import Resume
from interview_service.services.interview.session_state import InterviewSessionState
from interview_service.services.interview.report import generate_and_persist_report
from interview_service.services.interview.events import EventKind
from interview_service.services.interview.runner import InterviewRunner
from shared.capabilities.ai.llm.client import LLMClient

router = APIRouter()
logger = logging.getLogger(__name__)

# 强类型 ChatMessage 列表校验（防御存储层历史脏数据）
_CHAT_MSG_ADAPTER: TypeAdapter[list[ChatMessage]] = TypeAdapter(list[ChatMessage])


@router.get(
    "/resumes",
    response_model=list[ResumePickerItem],
    dependencies=[Depends(require_local_peer)],
)
def list_resume_picker(db: Session = Depends(get_db)):
    """配置页下拉用的简历摘要；不返回解析正文与深度评价。"""
    rows = db.query(Resume).order_by(Resume.created_at.desc()).all()
    return [
        ResumePickerItem(
            id=r.id,
            filename=r.filename,
            is_active=bool(r.is_active),
            score=r.score,
        )
        for r in rows
    ]


@router.post(
    "/sessions",
    response_model=InterviewSessionResponse,
    dependencies=[
        Depends(require_local_peer),
        Depends(
            rate_limit_dep(
                key="session_create",
                limit=DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
            )
        ),
    ],
)
def create_session(
    config: InterviewConfig,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = new_access_token()
    session = InterviewSession(
        role=config.role,
        level=config.level,
        company=config.company,
        workflow_type=config.workflow_type,
        personality=config.personality,
        strictness=config.strictness,
        interview_style=config.interview_style,
        resume_id=config.resume_id,
        avatar_id=config.avatar_id,
        scene_id=config.scene_id,
        status=SessionStatus.PENDING.value,
        current_phase="identity_check",
        access_token=token,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    set_session_cookie(
        response,
        scope="iv",
        session_id=session.id,
        token=token,
        secure=cookie_should_be_secure(request),
    )
    # 令牌仅经 HttpOnly Cookie 下发，响应体不再回传
    return _to_response(session, include_token=False)


@router.get(
    "/sessions",
    response_model=list[InterviewSessionResponse],
    dependencies=[Depends(require_local_peer)],
)
def list_sessions(db: Session = Depends(get_db)):
    """历史列表：仅返回元数据，不含 access_token（防枚举窃取能力令牌）。"""
    sessions = db.query(InterviewSession).order_by(InterviewSession.created_at.desc()).all()
    return [_to_response(s, include_token=False) for s in sessions]


@router.get("/sessions/{session_id}", response_model=InterviewSessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    return _to_response(session)


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


@router.post(
    "/sessions/{session_id}/start",
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def start_interview(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status not in (SessionStatus.PENDING.value, SessionStatus.ACTIVE.value):
        raise_error("A2002")

    llm = LLMClient.from_db(db)
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


@router.post(
    "/sessions/{session_id}/message",
    response_model=InterviewMessageResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def send_message(
    session_id: int,
    body: InterviewMessageRequest,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status == SessionStatus.COMPLETED.value:
        raise_error("A2002")

    llm = LLMClient.from_db(db)
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
            await generate_and_persist_report(session, llm, db)
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


@router.post(
    "/sessions/{session_id}/finish",
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def finish_interview(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
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
        return {"session_id": session_id, "status": "already_completed"}

    # 口头收尾可能已把 status 标 completed 但 report 仍空：补生成
    llm = LLMClient.from_db(db)
    try:
        await generate_and_persist_report(session, llm, db)
    except Exception as e:
        logger.exception("报告生成失败 sid=%s", session_id)
        raise_error("C1001", cause=e)
    return {
        "session_id": session_id,
        "status": SessionStatus.COMPLETED.value,
        "overall_score": session.overall_score,
    }


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    raw = json.loads(session.messages or "[]")
    # 强校验：仅保留符合 ChatMessage 结构的合法项；坏数据降级为空列表
    try:
        validated = _CHAT_MSG_ADAPTER.validate_python(raw)
        return [m.model_dump(mode="json") for m in validated]
    except Exception:
        # 历史脏数据：返回空，避免对外暴露内部异常
        return []


def _to_response(
    session: InterviewSession, *, include_token: bool = False
) -> InterviewSessionResponse:
    return InterviewSessionResponse(
        id=session.id,
        role=session.role,
        level=session.level,
        company=session.company,
        workflow_type=session.workflow_type,
        personality=session.personality,
        strictness=session.strictness,
        interview_style=session.interview_style,
        avatar_id=getattr(session, "avatar_id", None) or "professional_male",
        scene_id=getattr(session, "scene_id", None) or "meeting_room",
        status=session.status,
        current_phase=session.current_phase,
        overall_score=session.overall_score,
        started_at=session.started_at,
        ended_at=session.ended_at,
        created_at=session.created_at,
        access_token=(session.access_token if include_token else None),
    )
