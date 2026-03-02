"""Initial schema — all tables.

Revision ID: 001
Revises: (none)
Create Date: 2026-03-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PostgreSQL native UUID
_UUID = sa.UUID(as_uuid=True)


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("sso_provider", sa.String(32), nullable=True),
        sa.Column("sso_sub", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("sso_provider", "sso_sub", name="uq_users_sso_identity"),
    )

    # ── workspaces ─────────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("language_pref", sa.String(16), nullable=False, server_default="en"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ── user_channels ──────────────────────────────────────────────────────────
    op.create_table(
        "user_channels",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("user_telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("web_chat_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", name="uq_user_channels_workspace_id"),
    )

    # ── shared_email_accounts ──────────────────────────────────────────────────
    op.create_table(
        "shared_email_accounts",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("provider_type", sa.String(32), nullable=False),   # imap | gmail | graph
        sa.Column("credentials_ref", sa.String(512), nullable=False), # vault/kms ref — never plaintext
        sa.Column("from_alias", sa.String(255), nullable=False),
        sa.Column("signature_template", sa.String(2048), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

    # ── agents ─────────────────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role_prompt", sa.String(8192), nullable=False),
        sa.Column("allowed_tools", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("telegram_bot_token_ref", sa.String(512), nullable=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("rate_limit_per_min", sa.Integer, nullable=False, server_default="10"),
        sa.Column("max_concurrency", sa.Integer, nullable=False, server_default="3"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

    # ── agent_containers ───────────────────────────────────────────────────────
    op.create_table(
        "agent_containers",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("agent_id", _UUID, nullable=False),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("container_id", sa.String(64), nullable=True),
        sa.Column("container_name", sa.String(255), nullable=True),
        sa.Column("image", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column("restart_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.UniqueConstraint("agent_id", name="uq_agent_containers_agent_id"),
    )

    # ── threads ────────────────────────────────────────────────────────────────
    op.create_table(
        "threads",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("linked_telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("linked_email_thread_id", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

    # ── messages ───────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("thread_id", _UUID, nullable=False),
        sa.Column("sender_type", sa.String(32), nullable=False),  # user | agent | system | external
        sa.Column("sender_id", _UUID, nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),       # web | telegram | email | system
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_thread_id_created_at", "messages", ["thread_id", "created_at"])

    # ── tasks ──────────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("thread_id", _UUID, nullable=False),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("created_by", _UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )

    # ── task_steps ─────────────────────────────────────────────────────────────
    op.create_table(
        "task_steps",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("task_id", _UUID, nullable=False),
        sa.Column("agent_id", _UUID, nullable=False),
        sa.Column("step_type", sa.String(32), nullable=False),  # plan | action | message
        sa.Column("tool_call", sa.JSON, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
    )

    # ── approvals ──────────────────────────────────────────────────────────────
    op.create_table(
        "approvals",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("thread_id", _UUID, nullable=True),
        sa.Column("task_id", _UUID, nullable=True),
        sa.Column("approval_type", sa.String(64), nullable=False),
        sa.Column("requested_by", _UUID, nullable=False),       # agent_id or system UUID
        sa.Column("approved_by", _UUID, nullable=True),         # user_id
        sa.Column("scope", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_approvals_workspace_status", "approvals", ["workspace_id", "status"])

    # ── audit_logs ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),  # user | agent | system
        sa.Column("actor_id", _UUID, nullable=True),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", _UUID, nullable=True),
        sa.Column("detail", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_audit_logs_workspace_id_created_at", "audit_logs", ["workspace_id", "created_at"])

    # ── llm_configs ────────────────────────────────────────────────────────────
    op.create_table(
        "llm_configs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("agent_id", _UUID, nullable=True),   # NULL = workspace default
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=True),
        sa.Column("api_base_url", sa.String(512), nullable=True),
        sa.Column("max_tokens", sa.Integer, nullable=False, server_default="4096"),
        sa.Column("temperature", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "agent_id", name="uq_llm_config_scope"),
    )


def downgrade() -> None:
    op.drop_table("llm_configs")
    op.drop_index("ix_audit_logs_workspace_id_created_at", "audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_approvals_workspace_status", "approvals")
    op.drop_table("approvals")
    op.drop_table("task_steps")
    op.drop_table("tasks")
    op.drop_index("ix_messages_thread_id_created_at", "messages")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("agent_containers")
    op.drop_table("agents")
    op.drop_table("shared_email_accounts")
    op.drop_table("user_channels")
    op.drop_table("workspaces")
    op.drop_table("users")
