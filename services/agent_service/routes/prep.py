"""面试准备 API。

SSE 流式错误仅返回脱敏后的提示文案，原始异常走 logger.exception。
可变操作要求创建时下发的 capability token（``X-Interview-Token``）。
"""

import json
import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent_service.agents.prep.agent import PrepAgent
from shared.core.errors import raise_error
from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
    MAX_USER_TEXT_CHARS,
    SessionStatus,
)
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep
from shared.core.security import redact_api_key
from shared.core.session_auth import (
    assert_session_token,
    cookie_should_be_secure,
    extract_prep_token,
    new_access_token,
    set_session_cookie,
)
from shared.database import get_db
from agent_service.models import PrepSession
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)
router = APIRouter()

# SSE 错误事件统一文案（防止上游异常文本泄露 API Key / 内部细节）
_SSE_ERR_GENERIC = "辅导生成失败，请稍后重试"
_PREP_FORBIDDEN = "无权访问该辅导会话"


class PrepCreateRequest(BaseModel):
    resume_id: int | None = None
    target_role: str = ""
    target_company: str = ""


class PrepMessageRequest(BaseModel):
    content: str = Field(..., max_length=MAX_USER_TEXT_CHARS)


@router.post(
    "/sessions",
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
async def create_prep_session(
    body: PrepCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
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
    return {"id": session.id}


@router.post(
    "/sessions/{session_id}/message",
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def prep_message(
    session_id: int,
    body: PrepMessageRequest,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_prep_token),
):
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    llm = LLMClient.from_db(db)
    agent = PrepAgent(session, llm)
    reply = await agent.chat(body.content, db)
    return {"reply": reply, "token_usage": session.token_usage}


@router.post(
    "/sessions/{session_id}/message/stream",
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def prep_message_stream(
    session_id: int,
    body: PrepMessageRequest,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_prep_token),
):
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    llm = LLMClient.from_db(db)
    agent = PrepAgent(session, llm)

    async def event_stream():
        try:
            async for chunk in agent.chat_stream(body.content, db):
                if isinstance(chunk, dict):
                    # Agent 产出的结构化事件（如 search_results）直接透传
                    event = chunk if chunk.get("type") else {"type": "token", "content": str(chunk)}
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'token_usage': session.token_usage})}\n\n"
        except Exception as e:
            # 脱敏：仅写日志原文，对外只返通用文案
            safe_detail = redact_api_key(str(e)) or _SSE_ERR_GENERIC
            logger.exception("Prep 流式生成失败 sid=%s: %s", session_id, safe_detail)
            yield f"data: {json.dumps({'type': 'error', 'message': _SSE_ERR_GENERIC, 'code': 'C0001', 'retryable': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/messages")
def get_prep_messages(
    session_id: int,
    db: Session = Depends(get_db),
    access: str | None = Depends(extract_prep_token),
):
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    return json.loads(session.messages or "[]")
