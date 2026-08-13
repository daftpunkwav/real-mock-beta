"""baseline: 历史列补全（幂等）

Revision ID: 20260803_0001
Revises:
Create Date: 2026-08-03

将既有 ``app.core.migrate.MIGRATIONS`` 纳入 Alembic 版本链；
upgrade 调用 ``apply_column_migrations``，对已有列安全跳过。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260803_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from shared.core.migrate import apply_column_migrations

    bind = op.get_bind()
    # Engine 或 Connection 均可：apply 使用 begin()/inspect
    engine = bind.engine if hasattr(bind, "engine") else bind
    apply_column_migrations(engine)


def downgrade() -> None:
    # SQLite 列删除成本高；基线 revision 不支持自动 downgrade
    pass
