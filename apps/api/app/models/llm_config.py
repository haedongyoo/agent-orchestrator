"""
LLMConfig — per-workspace and per-agent LLM provider configuration.

Hierarchy (highest priority wins when spawning an agent container):
  1. Agent-level override  (agent_id IS NOT NULL)
  2. Workspace default     (agent_id IS NULL)
  3. Env-var fallback      (LLM_MODEL / LLM_API_KEY in docker-compose)

API keys are stored Fernet-encrypted (see services/secrets.py).
The raw key is NEVER stored in plaintext and NEVER returned to clients.
Clients receive `has_api_key: bool` instead.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, DateTime, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class LLMConfig(Base):
    __tablename__ = "llm_configs"
    __table_args__ = (
        # One config per scope: (workspace, agent=None) = workspace default,
        #                       (workspace, agent=X)    = per-agent override
        UniqueConstraint("workspace_id", "agent_id", name="uq_llm_config_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL  → workspace-level default config
    # SET   → per-agent override (takes precedence over workspace default)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
    )

    # LiteLLM model string — includes provider prefix where needed.
    # Examples: "anthropic/claude-opus-4-6", "gpt-4o", "ollama/llama3.3"
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    # API key — Fernet-encrypted, base64-encoded.  NULL for providers that
    # don't require a key (e.g. Ollama) or when using IAM/instance roles (Bedrock).
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Custom base URL — required for Ollama, Azure OpenAI custom deployments, etc.
    # Stored in plaintext (not a secret).
    api_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Generation parameters
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[float] = mapped_column(Float, default=1.0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
