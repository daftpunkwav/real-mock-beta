"""rate_limit_buckets 表

Revision ID: 20260901_0004
Revises: 20260901_0003
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "20260901_0004"
down_revision: Union[str, None] = "20260901_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "CREATE TABLE IF NOT EXISTS rate_limit_buckets ("
            "bucket_key VARCHAR(128) PRIMARY KEY, "
            "timestamps_json TEXT DEFAULT '[]', "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    pass
