"""Add agent_id to threads table.

Revision ID: 003
Revises: 002
Create Date: 2026-03-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_threads_agent_id", "threads", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_threads_agent_id", table_name="threads")
    op.drop_column("threads", "agent_id")
