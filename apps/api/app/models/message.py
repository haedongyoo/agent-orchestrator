import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id"), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)  # user | agent | system | external
    sender_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)   # user_id or agent_id
    channel: Mapped[str] = mapped_column(String(32), nullable=False)      # web | telegram | email | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: language, attachments, email headers, telegram message_id, etc.
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    thread: Mapped["Thread"] = relationship(back_populates="messages")  # type: ignore[name-defined]
