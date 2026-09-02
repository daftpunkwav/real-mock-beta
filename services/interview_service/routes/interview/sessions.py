"""面试会话 CRUD：简历 picker、创建/列表/单查、消息列表与响应视图。

这些 handler 挂到 ``interview`` 主路由（见 ``interview.py`` 的组装）；本模块
不带 router 前缀，仅定义无装饰器 handler 供主文件 include。
"""

from __future__ import annotations

import json

from fastapi import Depends, Request, Response
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from shared.core.constants import SessionStatus
from shared.core.errors import raise_error
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
    InterviewSessionResponse,
)
from shared.services.resume_picker import list_resume_picker_items


# 强类型 ChatMessage 列表校验（防御存储层历史脏数据）
_CHAT_MSG_ADAPTER: TypeAdapter[list[ChatMessage]] = TypeAdapter(list[ChatMessage])


def list_resume_picker(db: Session = Depends(get_db)):
    """配置页下拉用的简历摘要；不返回解析正文与深度评价。"""
    return list_resume_picker_items(db)


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
        ai_overrides=(
            json.dumps(config.ai_overrides.model_dump(exclude_none=True), ensure_ascii=False)
            if config.ai_overrides
            else "{}"
        ),
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


def list_sessions(db: Session = Depends(get_db)):
    """历史列表：仅返回元数据，不含 access_token（防枚举窃取能力令牌）。"""
    sessions = db.query(InterviewSession).order_by(InterviewSession.created_at.desc()).all()
    return [_to_response(s, include_token=False) for s in sessions]


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
