from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open")  # open | closed
    linked_telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    linked_email_thread_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped["Workspace"] = relationship(back_populates="threads")  # type: ignore[name-defined]
    agent: Mapped[Optional["Agent"]] = relationship()  # type: ignore[name-defined]
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", order_by="Message.created_at")
    tasks: Mapped[list["Task"]] = relationship(back_populates="thread")  # type: ignore[name-defined]
