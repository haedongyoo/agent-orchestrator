from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Prevent duplicate SSO identities; NULLs are distinct (email/password users unaffected)
        UniqueConstraint("sso_provider", "sso_sub", name="uq_users_sso_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # SSO fields — set for OAuth2 users; NULL for email/password users
    sso_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # google | github | microsoft
    sso_sub: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)        # stable user ID from provider
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
    allowed_email_domains: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="workspaces")
    agents: Mapped[list["Agent"]] = relationship(back_populates="workspace")  # type: ignore[name-defined]
    threads: Mapped[list["Thread"]] = relationship(back_populates="workspace")  # type: ignore[name-defined]
    vendors: Mapped[list["Vendor"]] = relationship(back_populates="workspace")  # type: ignore[name-defined]


class UserChannel(Base):
    """Per-workspace channel config for the human user."""
    __tablename__ = "user_channels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, unique=True)
    user_telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    web_chat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SharedEmailAccount(Base):
    """Shared email inbox usable by agents in the workspace."""
    __tablename__ = "shared_email_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)  # imap | gmail | graph
    credentials_ref: Mapped[str] = mapped_column(String(512), nullable=False)  # vault/kms reference — never plaintext
    from_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    signature_template: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
