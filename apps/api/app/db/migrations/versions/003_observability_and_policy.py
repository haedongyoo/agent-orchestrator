"""Add observability (step_traces, task_step metrics) and policy hardening (allowed_email_domains).

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

_UUID = sa.UUID(as_uuid=True)


def upgrade() -> None:
    # ── step_traces table (Observability — PR 2) ──────────────────────────────
    op.create_table(
        "step_traces",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("step_id", _UUID, sa.ForeignKey("task_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("detail", sa.JSON, nullable=True),
    )
    op.create_index("ix_step_traces_step_timestamp", "step_traces", ["step_id", "timestamp"])

    # ── TaskStep metric columns (Observability — PR 2) ────────────────────────
    op.add_column("task_steps", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_steps", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_steps", sa.Column("duration_ms", sa.Integer, nullable=True))
    op.add_column("task_steps", sa.Column("input_tokens", sa.Integer, nullable=True))
    op.add_column("task_steps", sa.Column("output_tokens", sa.Integer, nullable=True))
    op.add_column("task_steps", sa.Column("iterations", sa.Integer, nullable=True))
    op.add_column("task_steps", sa.Column("agent_model", sa.String(128), nullable=True))

    # ── Workspace allowed_email_domains (Policy Hardening — PR 3) ─────────────
    op.add_column("workspaces", sa.Column("allowed_email_domains", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "allowed_email_domains")

    op.drop_column("task_steps", "agent_model")
    op.drop_column("task_steps", "iterations")
    op.drop_column("task_steps", "output_tokens")
    op.drop_column("task_steps", "input_tokens")
    op.drop_column("task_steps", "duration_ms")
    op.drop_column("task_steps", "completed_at")
    op.drop_column("task_steps", "started_at")

    op.drop_index("ix_step_traces_step_timestamp", "step_traces")
    op.drop_table("step_traces")
