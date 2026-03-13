"""
Email OAuth router — connect Gmail or Microsoft 365 email accounts via OAuth2.

Flow:
  GET  /api/email-oauth/{provider}/authorize?workspace_id=...
       → 302 redirect to provider consent page (Gmail or Microsoft)

  GET  /api/email-oauth/{provider}/callback?code=...&state=...
       → exchange code → store tokens → create SharedEmailAccount

Supported providers: gmail, graph (Microsoft Graph / Office 365)
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.workspace import User, Workspace, SharedEmailAccount
from app.services.auth import get_current_user
from app.services.email_oauth import (
    SUPPORTED_EMAIL_PROVIDERS,
    build_email_auth_url,
    create_email_oauth_state,
    exchange_email_code,
    package_oauth_credentials,
    verify_email_oauth_state,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class EmailOAuthResult(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    provider_type: str
    from_alias: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{provider}/authorize")
async def email_oauth_authorize(
    provider: str,
    workspace_id: uuid.UUID = Query(..., description="Workspace to link the email account to"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Start email OAuth flow — redirect to provider consent page.

    Requires the workspace to be owned by the current user.
    The state token encodes workspace_id for the callback.
    """
    if provider not in SUPPORTED_EMAIL_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported email provider '{provider}'. Supported: {sorted(SUPPORTED_EMAIL_PROVIDERS)}",
        )

    # Verify workspace ownership
    ws = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    if ws.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    state = create_email_oauth_state(provider, str(workspace_id))
    url = build_email_auth_url(provider, state)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/{provider}/callback")
async def email_oauth_callback(
    provider: str,
    code: str,
    state: str,
    redirect_uri: Optional[str] = Query(None, description="Frontend redirect after success"),
    db: AsyncSession = Depends(get_db),
) -> EmailOAuthResult:
    """
    Handle OAuth2 callback from email provider.

    Exchanges code for tokens, creates a SharedEmailAccount, and returns
    the account details. Tokens are Fernet-encrypted before DB storage.
    """
    if provider not in SUPPORTED_EMAIL_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported email provider: {provider}",
        )

    # Exchange code for tokens (also verifies state)
    tokens = await exchange_email_code(provider, code, state)

    # Extract workspace_id from state
    workspace_id = verify_email_oauth_state(state, provider)

    # Package and encrypt credentials
    credentials_ref = package_oauth_credentials(provider, tokens)

    # Create or update shared email account
    result = await db.execute(
        select(SharedEmailAccount).where(
            SharedEmailAccount.workspace_id == uuid.UUID(workspace_id),
            SharedEmailAccount.provider_type == provider,
            SharedEmailAccount.from_alias == tokens.email,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.credentials_ref = credentials_ref
        existing.is_active = True
        account = existing
    else:
        account = SharedEmailAccount(
            workspace_id=uuid.UUID(workspace_id),
            provider_type=provider,
            credentials_ref=credentials_ref,
            from_alias=tokens.email,
            is_active=True,
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)

    if redirect_uri:
        from urllib.parse import urlencode
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(
            url=f"{redirect_uri}{sep}{urlencode({'email_account_id': str(account.id)})}",
            status_code=status.HTTP_302_FOUND,
        )

    return EmailOAuthResult(
        id=account.id,
        workspace_id=account.workspace_id,
        provider_type=account.provider_type,
        from_alias=account.from_alias,
        is_active=account.is_active,
    )
