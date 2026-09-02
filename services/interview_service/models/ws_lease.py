"""WebSocket 会话租约（DB 持久化，多 worker 可见）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WsSessionLease(SessionsBase):
    """同 session 仅允许一条活跃 WS 的分布式租约表。"""

    __tablename__ = "ws_session_leases"
    __table_args__ = (UniqueConstraint("session_id", name="uq_ws_session_leases_session_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    lease_token: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
