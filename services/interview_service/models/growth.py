"""成长记录 ORM。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GrowthRecord(SessionsBase):
    """用户成长记录。"""

    __tablename__ = "growth_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    session_id: Mapped[int] = mapped_column(Integer)
    weak_skills: Mapped[str] = mapped_column(Text, default="[]")
    common_mistakes: Mapped[str] = mapped_column(Text, default="[]")
    training_plan: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
