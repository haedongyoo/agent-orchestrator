from __future__ import annotations
"""
Vendor/Contractor CRM router.

Endpoints:
  GET    /api/workspaces/{workspace_id}/vendors              → 200 list[VendorResponse]
  POST   /api/workspaces/{workspace_id}/vendors              → 201 VendorResponse  (upsert)
  GET    /api/workspaces/{workspace_id}/vendors/{vendor_id}  → 200 VendorResponse
  PUT    /api/workspaces/{workspace_id}/vendors/{vendor_id}  → 200 VendorResponse
  DELETE /api/workspaces/{workspace_id}/vendors/{vendor_id}  → 204

All endpoints require Bearer JWT and are scoped to the authenticated workspace owner.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.workspace import Workspace
from app.models.vendor import Vendor
from app.services.auth import get_current_user
from app.services.vendors import (
    delete_vendor,
    get_vendor,
    list_vendors,
    upsert_vendor,
)
from app.models.workspace import User

router = APIRouter()

_VALID_CATEGORIES = frozenset({
    "furniture_supplier",
    "material_factory",
    "contractor",
    "logistics",
    "other",
})


# ── Schemas ────────────────────────────────────────────────────────────────────

class VendorUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=64)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    website: Optional[str] = Field(default=None, max_length=512)
    country: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class VendorUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=64)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    website: Optional[str] = Field(default=None, max_length=512)
    country: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class VendorResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    email: Optional[str]
    category: Optional[str]
    contact_name: Optional[str]
    phone: Optional[str]
    website: Optional[str]
    country: Optional[str]
    notes: Optional[str]
    tags: list
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_workspace_or_404(
    workspace_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


def _validate_category(category: Optional[str]) -> None:
    if category is not None and category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category must be one of: {sorted(_VALID_CATEGORIES)}",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/{workspace_id}/vendors",
    response_model=list[VendorResponse],
)
async def list_workspace_vendors(
    workspace_id: uuid.UUID,
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_workspace_or_404(workspace_id, db, current_user)
    vendors = await list_vendors(db, workspace_id, category=category, limit=limit, offset=offset)
    return vendors


@router.post(
    "/{workspace_id}/vendors",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_workspace_vendor(
    workspace_id: uuid.UUID,
    body: VendorUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_workspace_or_404(workspace_id, db, current_user)
    _validate_category(body.category)
    vendor = await upsert_vendor(
        db,
        workspace_id=workspace_id,
        name=body.name,
        email=body.email,
        category=body.category,
        contact_name=body.contact_name,
        phone=body.phone,
        website=body.website,
        country=body.country,
        notes=body.notes,
        tags=body.tags,
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.get(
    "/{workspace_id}/vendors/{vendor_id}",
    response_model=VendorResponse,
)
async def get_workspace_vendor(
    workspace_id: uuid.UUID,
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_workspace_or_404(workspace_id, db, current_user)
    vendor = await get_vendor(db, workspace_id, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return vendor


@router.put(
    "/{workspace_id}/vendors/{vendor_id}",
    response_model=VendorResponse,
)
async def update_workspace_vendor(
    workspace_id: uuid.UUID,
    vendor_id: uuid.UUID,
    body: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_workspace_or_404(workspace_id, db, current_user)
    vendor = await get_vendor(db, workspace_id, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    _validate_category(body.category)
    if body.email is not None:
        vendor.email = body.email
    if body.category is not None:
        vendor.category = body.category
    if body.contact_name is not None:
        vendor.contact_name = body.contact_name
    if body.phone is not None:
        vendor.phone = body.phone
    if body.website is not None:
        vendor.website = body.website
    if body.country is not None:
        vendor.country = body.country
    if body.notes is not None:
        vendor.notes = body.notes
    if body.tags is not None:
        vendor.tags = body.tags
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.delete(
    "/{workspace_id}/vendors/{vendor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_workspace_vendor(
    workspace_id: uuid.UUID,
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_workspace_or_404(workspace_id, db, current_user)
    deleted = await delete_vendor(db, workspace_id, vendor_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    await db.commit()
