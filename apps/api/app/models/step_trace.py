from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


# Valid event types for step traces
TRACE_EVENT_TYPES = (
    "enqueued",
    "started",
    "llm_request",
    "llm_response",
    "tool_call",
    "tool_result",
    "completed",
    "error",
    "rate_limit",
)


class StepTrace(Base):
    """Fine-grained execution event within a task step. Append-only."""
    __tablename__ = "step_traces"
    __table_args__ = (
        Index("ix_step_traces_step_timestamp", "step_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_steps.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    step: Mapped["TaskStep"] = relationship(back_populates="traces")  # type: ignore[name-defined]
