import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_prompt: Mapped[str] = mapped_column(String(8192), nullable=False)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["send_email", "send_telegram"]
    telegram_bot_token_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)  # vault/kms ref
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=10)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped["Workspace"] = relationship(back_populates="agents")  # type: ignore[name-defined]
    task_steps: Mapped[list["TaskStep"]] = relationship(back_populates="agent")  # type: ignore[name-defined]
    container: Mapped["AgentContainer | None"] = relationship(  # type: ignore[name-defined]
        back_populates="agent",
        uselist=False,
        cascade="all, delete-orphan",
    )
