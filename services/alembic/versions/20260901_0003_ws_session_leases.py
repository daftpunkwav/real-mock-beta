"""ws_session_leases 表

Revision ID: 20260901_0003
Revises: 20260901_0002
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "20260901_0003"
down_revision: Union[str, None] = "20260901_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "CREATE TABLE IF NOT EXISTS ws_session_leases ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id INTEGER NOT NULL, "
            "lease_token VARCHAR(64) NOT NULL, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    bind.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ws_session_leases_session_id "
            "ON ws_session_leases (session_id)"
        )
    )


def downgrade() -> None:
    pass
