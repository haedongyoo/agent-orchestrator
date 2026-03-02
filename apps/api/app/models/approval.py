from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow

# Approval types
APPROVAL_TYPES = (
    "enable_agent_chat",   # A2A communication
    "send_email",          # outbound email
    "new_recipient",       # emailing a new address
    "share_info",          # agent sharing info with another
    "other",
)
APPROVAL_STATUSES = ("pending", "approved", "rejected")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    thread_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("threads.id"), nullable=True)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    approval_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(nullable=False)  # agent_id or system
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    # scope: { agents: [...], duration_seconds: N, recipients: [...], thread_limit: T, content_types: [...] }
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
