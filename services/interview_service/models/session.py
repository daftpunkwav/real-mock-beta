"""模拟面试会话 ORM。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewSession(Base):
    """面试会话记录。"""

    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(50))
    company: Mapped[str] = mapped_column(String(100))
    workflow_type: Mapped[str] = mapped_column(String(50), default="technical")
    personality: Mapped[str] = mapped_column(String(50), default="professional")
    strictness: Mapped[int] = mapped_column(Integer, default=3)
    interview_style: Mapped[str] = mapped_column(String(50), default="deep_dive")
    avatar_id: Mapped[str] = mapped_column(String(50), default="professional_male")
    scene_id: Mapped[str] = mapped_column(String(50), default="meeting_room")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    current_phase: Mapped[str] = mapped_column(String(50), default="identity_check")
    agent_state: Mapped[str] = mapped_column(Text, default="{}")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    report: Mapped[str] = mapped_column(Text, default="{}")
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    access_token: Mapped[str] = mapped_column(String(64), default="")
    ai_overrides: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
