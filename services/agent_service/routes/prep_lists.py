"""Prep 只读列表：简历下拉摘要与辅导会话列表。

仅本机可访问；列表类接口不含消息正文与能力令牌。
"""

from __future__ import annotations

import json

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from agent_service.models import PrepSession
from shared.database import get_db
from shared.models import Resume
from shared.services.resume_picker import list_resume_picker_items


def list_resume_picker(db: Session = Depends(get_db)):
    """准备页下拉用的简历摘要；不返回解析正文与深度评价。"""
    return list_resume_picker_items(db)


def list_prep_sessions(db: Session = Depends(get_db)):
    """辅导会话列表（前端「对话记录」按简历分组展示）。

    仅本机可访问；只返回摘要（首条提问 + 消息数 + 归属简历），
    不含消息正文与能力令牌——打开具体会话仍走原 token 校验。
    """
    rows = (
        db.query(PrepSession)
        .order_by(func.coalesce(PrepSession.updated_at, PrepSession.created_at).desc())
        .all()
    )
    names = {r.id: r.filename for r in db.query(Resume).all()}
    items: list[dict] = []
    for s in rows:
        try:
            msgs = json.loads(s.messages or "[]")
        except json.JSONDecodeError:
            msgs = []
        summary = next(
            (
                str(m.get("content") or "").strip()
                for m in msgs
                if m.get("role") == "user" and m.get("content")
            ),
            "",
        )
        items.append(
            {
                "id": s.id,
                "resume_id": s.resume_id,
                "resume_filename": names.get(s.resume_id) if s.resume_id else None,
                "summary": summary[:48],
                "message_count": sum(
                    1
                    for m in msgs
                    if m.get("role") in ("user", "assistant") and m.get("content")
                ),
                "status": getattr(s, "status", "") or "active",
                "token_usage": s.token_usage or 0,
                "prompt_tokens": s.prompt_tokens or 0,
                "completion_tokens": s.completion_tokens or 0,
                "cached_tokens": s.cached_tokens or 0,
                "created_at": s.created_at,
                "updated_at": getattr(s, "updated_at", None) or s.created_at,
            }
        )
    return items
