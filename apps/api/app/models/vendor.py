from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Vendor(Base):
    """
    Vendor / contractor profile in the workspace CRM.

    Created/updated by the upsert_vendor agent tool (via orchestrator).
    Also manageable directly via the REST API.

    Unique per workspace by name — upsert_vendor matches on (workspace_id, name).
    """
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_vendors_workspace_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="vendors")  # type: ignore[name-defined]
