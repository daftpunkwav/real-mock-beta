"""智能体服务业务模型：面试准备会话。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PrepSession(Base):
    """面试准备辅导会话。"""

    __tablename__ = "prep_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_role: Mapped[str] = mapped_column(String(100), default="")
    target_company: Mapped[str] = mapped_column(String(100), default="")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    # 与 shared.core.migrate 中 prep_sessions.status 一致；缺列时启动迁移会补齐
    status: Mapped[str] = mapped_column(String(20), default="active")
    # 能力令牌：创建时下发，message/history 必验
    access_token: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


__all__ = ["PrepSession"]
