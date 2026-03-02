import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="owner")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    language_pref: Mapped[str] = mapped_column(String(16), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="workspaces")
    agents: Mapped[list["Agent"]] = relationship(back_populates="workspace")  # type: ignore[name-defined]
    threads: Mapped[list["Thread"]] = relationship(back_populates="workspace")  # type: ignore[name-defined]


class UserChannel(Base):
    """Per-workspace channel config for the human user."""
    __tablename__ = "user_channels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, unique=True)
    user_telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    web_chat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SharedEmailAccount(Base):
    """Shared email inbox usable by agents in the workspace."""
    __tablename__ = "shared_email_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)  # imap | gmail | graph
    credentials_ref: Mapped[str] = mapped_column(String(512), nullable=False)  # vault/kms reference — never plaintext
    from_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    signature_template: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
