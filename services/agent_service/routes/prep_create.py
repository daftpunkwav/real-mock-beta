"""Prep 会话创建：颁发能力令牌并下发 cookie。"""

from __future__ import annotations

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from agent_service.models import PrepSession
from agent_service.schemas import PrepCreateRequest, PrepSessionCreateResponse
from shared.core.constants import SessionStatus
from shared.core.session_auth import (
    cookie_should_be_secure,
    new_access_token,
    set_session_cookie,
)
from shared.database import get_sessions_db


async def create_prep_session(
    body: PrepCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_sessions_db),
):
    token = new_access_token()
    # status 列由模型 + migrate 保证；构造时显式写入 active
    kwargs: dict = {
        "resume_id": body.resume_id,
        "target_role": body.target_role,
        "target_company": body.target_company,
        "access_token": token,
    }
    # 兼容：若 ORM 已声明 status 则写入
    if hasattr(PrepSession, "status"):
        kwargs["status"] = SessionStatus.ACTIVE.value
    session = PrepSession(**kwargs)
    db.add(session)
    db.commit()
    db.refresh(session)
    set_session_cookie(
        response,
        scope="prep",
        session_id=session.id,
        token=token,
        secure=cookie_should_be_secure(request),
    )
    return PrepSessionCreateResponse(id=session.id)
