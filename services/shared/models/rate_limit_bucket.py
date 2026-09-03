"""进程间共享的限流桶（sessions.db，多 worker 部署）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RateLimitBucket(SessionsBase):
    """滑动窗口时间戳 JSON：``{key}:{client_id}`` -> ``[epoch_s, ...]``。

    时间戳为 wall-clock epoch 秒（``time.time()``）：DB 后端须跨进程与整机
    重启读取，monotonic 时钟无跨重启基准。
    """

    __tablename__ = "rate_limit_buckets"

    bucket_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamps_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
