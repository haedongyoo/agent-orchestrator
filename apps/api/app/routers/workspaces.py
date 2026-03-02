from __future__ import annotations
"""
Workspace router — CRUD for workspaces and shared email accounts.

Endpoints:
  POST   /api/workspaces                                   → 201 WorkspaceResponse
  GET    /api/workspaces/{workspace_id}                    → 200 WorkspaceResponse
  PUT    /api/workspaces/{workspace_id}                    → 200 WorkspaceResponse
  POST   /api/workspaces/{workspace_id}/shared-email       → 201 SharedEmailResponse
  PUT    /api/workspaces/{workspace_id}/shared-email/{id}  → 200 SharedEmailResponse

All mutating endpoints require Bearer JWT.
Workspace access is scoped to the authenticated user (owner).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.workspace import SharedEmailAccount, Workspace
from app.services.auth import get_current_user
from app.models.workspace import User

router = APIRouter()

_VALID_PROVIDERS = frozenset({"imap", "gmail", "graph"})


# ── Schemas ────────────────────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", max_length=64)
    language_pref: str = Field(default="en", max_length=16)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    timezone: Optional[str] = Field(default=None, max_length=64)
    language_pref: Optional[str] = Field(default=None, max_length=16)


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str
    language_pref: str

    model_config = {"from_attributes": True}


class SharedEmailCreate(BaseModel):
    provider_type: str = Field(description="imap | gmail | graph")
    credentials_ref: str = Field(min_length=1, max_length=512, description="Vault/KMS reference — never the secret itself")
    from_alias: str = Field(min_length=1, max_length=255)
    signature_template: Optional[str] = Field(default=None, max_length=2048)


class SharedEmailResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    provider_type: str
    from_alias: str
    signature_template: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_owned_workspace(
    workspace_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Workspace:
    """Return the workspace if it exists and belongs to current_user; else 404."""
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


async def _get_owned_email_account(
    workspace: Workspace,
    email_id: uuid.UUID,
    db: AsyncSession,
) -> SharedEmailAccount:
    result = await db.execute(
        select(SharedEmailAccount).where(
            SharedEmailAccount.id == email_id,
            SharedEmailAccount.workspace_id == workspace.id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared email account not found")
    return account


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Create a new workspace owned by the authenticated user."""
    workspace = Workspace(
        user_id=current_user.id,
        name=body.name,
        timezone=body.timezone,
        language_pref=body.language_pref,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Fetch a workspace. Returns 404 if not found or not owned by caller."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    return WorkspaceResponse.model_validate(workspace)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Partially update a workspace (only provided fields are changed)."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)

    if body.name is not None:
        workspace.name = body.name
    if body.timezone is not None:
        workspace.timezone = body.timezone
    if body.language_pref is not None:
        workspace.language_pref = body.language_pref

    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.post("/{workspace_id}/shared-email", response_model=SharedEmailResponse, status_code=status.HTTP_201_CREATED)
async def add_shared_email(
    workspace_id: uuid.UUID,
    body: SharedEmailCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SharedEmailResponse:
    """Add a shared email account to the workspace. credentials_ref must be a Vault/KMS key."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)

    if body.provider_type not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid provider_type '{body.provider_type}'. Must be one of: {sorted(_VALID_PROVIDERS)}",
        )

    account = SharedEmailAccount(
        workspace_id=workspace.id,
        provider_type=body.provider_type,
        credentials_ref=body.credentials_ref,
        from_alias=body.from_alias,
        signature_template=body.signature_template,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return SharedEmailResponse.model_validate(account)


@router.put("/{workspace_id}/shared-email/{email_id}", response_model=SharedEmailResponse)
async def update_shared_email(
    workspace_id: uuid.UUID,
    email_id: uuid.UUID,
    body: SharedEmailCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SharedEmailResponse:
    """Update a shared email account (full replace — all fields required)."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    account = await _get_owned_email_account(workspace, email_id, db)

    if body.provider_type not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid provider_type '{body.provider_type}'. Must be one of: {sorted(_VALID_PROVIDERS)}",
        )

    account.provider_type = body.provider_type
    account.credentials_ref = body.credentials_ref
    account.from_alias = body.from_alias
    account.signature_template = body.signature_template

    await db.commit()
    await db.refresh(account)
    return SharedEmailResponse.model_validate(account)
