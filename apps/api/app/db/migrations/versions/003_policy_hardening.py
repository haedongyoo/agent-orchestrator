"""Add allowed_email_domains to workspaces for policy hardening.

Revision ID: 003
Revises: 002
Create Date: 2026-03-04
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
        "workspaces",
        sa.Column("allowed_email_domains", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "allowed_email_domains")
