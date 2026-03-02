from typing import Optional
"""
AgentContainer — persistent registry of Docker container state per agent.

One record per agent. Updated in-place as the container lifecycle progresses.
The orchestrator uses this table as the authoritative source of truth for
which container belongs to which agent, and what its current status is.

Status state machine:
  none → starting → running → stopped
                  ↘ crashed → starting (auto-restart with backoff)
                  → unknown  (Docker API unreachable or container not found)
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow

CONTAINER_STATUSES = ("starting", "running", "stopped", "crashed", "unknown")


class AgentContainer(Base):
    __tablename__ = "agent_containers"
    __table_args__ = (
        UniqueConstraint("agent_id", name="uq_agent_containers_agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
    )

    # Docker identifiers — set on first spawn, updated on restart
    container_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)   # 64-char Docker hash
    container_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # openclaw-agent-{agent_id}
    image: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)           # image tag used

    # Lifecycle
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Crash tracking
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    restart_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    agent: Mapped["Agent"] = relationship(back_populates="container")  # type: ignore[name-defined]
