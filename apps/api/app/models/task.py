from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow

# Task status state machine:
# queued → running → blocked / needs_approval → done / failed
TASK_STATUSES = ("queued", "running", "blocked", "needs_approval", "done", "failed")
STEP_STATUSES = ("queued", "running", "done", "failed")
STEP_TYPES = ("plan", "action", "message")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id"), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    thread: Mapped["Thread"] = relationship(back_populates="tasks")  # type: ignore[name-defined]
    steps: Mapped[list["TaskStep"]] = relationship(back_populates="task", order_by="TaskStep.created_at")


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)  # plan | action | message
    tool_call: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Observability columns (populated from agent step result)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    iterations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agent_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    task: Mapped[Task] = relationship(back_populates="steps")
    agent: Mapped["Agent"] = relationship(back_populates="task_steps")  # type: ignore[name-defined]
    traces: Mapped[list["StepTrace"]] = relationship(back_populates="step", order_by="StepTrace.timestamp")  # type: ignore[name-defined]
