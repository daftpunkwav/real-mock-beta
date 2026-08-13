"""模拟面试域业务模型：面试会话与成长记录。

处理器配置模型（StageConfig / LLMSettings）与候选人数据（UserProfile /
Resume）位于 ``shared.models``，此处 re-export 以兼容服务内引用。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base
from shared.models import LLMSettings, StageConfig  # noqa: F401  # 共享配置 re-export


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
    # 能力令牌：创建时下发，可变操作必验；勿写入 list/get 响应
    access_token: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class GrowthRecord(Base):
    """用户成长记录。"""

    __tablename__ = "growth_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    session_id: Mapped[int] = mapped_column(Integer)
    weak_skills: Mapped[str] = mapped_column(Text, default="[]")
    common_mistakes: Mapped[str] = mapped_column(Text, default="[]")
    training_plan: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


__all__ = ["GrowthRecord", "InterviewSession"]
