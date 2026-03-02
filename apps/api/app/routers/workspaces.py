from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.session import get_db

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str
    timezone: str = "UTC"
    language_pref: str = "en"


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str
    language_pref: str

    class Config:
        from_attributes = True


class SharedEmailCreate(BaseModel):
    provider_type: str          # imap | gmail | graph
    credentials_ref: str        # vault/kms reference — never the actual secret
    from_alias: str
    signature_template: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, db: AsyncSession = Depends(get_db)):
    # TODO: get current user from JWT, create workspace
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(workspace_id: uuid.UUID, body: WorkspaceCreate, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{workspace_id}/shared-email", status_code=status.HTTP_201_CREATED)
async def add_shared_email(workspace_id: uuid.UUID, body: SharedEmailCreate, db: AsyncSession = Depends(get_db)):
    # TODO: validate credentials_ref format, persist SharedEmailAccount
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/{workspace_id}/shared-email/{email_id}")
async def update_shared_email(workspace_id: uuid.UUID, email_id: uuid.UUID, body: SharedEmailCreate, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")
