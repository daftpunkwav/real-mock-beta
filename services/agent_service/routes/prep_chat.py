"""Prep 会话对话：同步消息、SSE 流式与历史消息（能力令牌校验）。

SSE 流式错误仅返回脱敏后的提示文案，原始异常走 logger.exception。
可变操作要求创建时下发的 capability token（``X-Interview-Token``）。
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from agent_service.agents.prep.agent import PrepAgent
from agent_service.models import PrepSession
from agent_service.schemas import PrepHistoryMessage, PrepMessageRequest, PrepMessageResponse
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.ai.llm.stream_filters import sanitize_special_tokens
from shared.core.constants import SessionStatus
from shared.core.errors import raise_error
from shared.core.security import redact_api_key
from shared.core.session_auth import (
    assert_session_token,
    extract_prep_token,
)
from shared.database import get_api_db, get_sessions_db

logger = logging.getLogger(__name__)

# SSE 错误事件统一文案（防止上游异常文本泄露 API Key / 内部细节）
_SSE_ERR_GENERIC = "辅导生成失败，请稍后重试"
_PREP_FORBIDDEN = "无权访问该辅导会话"


def _build_prep_llm(api_db: Session, body: PrepMessageRequest) -> LLMClient:
    """按请求覆盖（可选）构建思考客户端（读 api 库配置）。"""
    return LLMClient.from_db(
        api_db,
        profile_id=body.model_profile_id,
        reasoning_effort=body.reasoning_effort,
    )


async def prep_message(
    session_id: int,
    body: PrepMessageRequest,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    access: str | None = Depends(extract_prep_token),
):
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    llm = _build_prep_llm(api_db, body)
    agent = PrepAgent(session, llm)
    reply = await agent.chat(body.content, db)
    return PrepMessageResponse(reply=reply, token_usage=session.token_usage or 0)


async def prep_message_stream(
    session_id: int,
    body: PrepMessageRequest,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    access: str | None = Depends(extract_prep_token),
):
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    llm = _build_prep_llm(api_db, body)
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


def get_prep_messages(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_prep_token),
):
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    messages = json.loads(session.messages or "[]")
    # 历史消息可能存有净化器上线前的模板 token 泄漏:展示前清洗(不改库)
    for m in messages:
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            m["content"] = sanitize_special_tokens(m["content"])
    return [PrepHistoryMessage.model_validate(m) for m in messages]
