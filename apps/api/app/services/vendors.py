"""
Vendor/Contractor CRM service.

upsert_vendor() is the primary entry point — called both from:
  - REST API (direct user action)
  - Agent tool result handler (after an agent calls upsert_vendor tool)

Upsert semantics: match on (workspace_id, name) — update all supplied
non-None fields on an existing vendor, create a new row otherwise.
"""
from __future__ import annotations

import uuid
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vendor import Vendor

log = structlog.get_logger()


async def upsert_vendor(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    email: Optional[str] = None,
    category: Optional[str] = None,
    contact_name: Optional[str] = None,
    phone: Optional[str] = None,
    website: Optional[str] = None,
    country: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[list] = None,
) -> Vendor:
    """
    Create or update a vendor by (workspace_id, name).
    Only non-None keyword arguments overwrite existing values.
    Returns the persisted Vendor (not yet committed — caller must commit).
    """
    result = await db.execute(
        select(Vendor).where(
            Vendor.workspace_id == workspace_id,
            Vendor.name == name,
        )
    )
    vendor = result.scalar_one_or_none()

    if vendor is None:
        vendor = Vendor(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name=name,
            email=email,
            category=category,
            contact_name=contact_name,
            phone=phone,
            website=website,
            country=country,
            notes=notes,
            tags=tags or [],
        )
        db.add(vendor)
        log.info("vendor.created", workspace_id=str(workspace_id), name=name)
    else:
        if email is not None:
            vendor.email = email
        if category is not None:
            vendor.category = category
        if contact_name is not None:
            vendor.contact_name = contact_name
        if phone is not None:
            vendor.phone = phone
        if website is not None:
            vendor.website = website
        if country is not None:
            vendor.country = country
        if notes is not None:
            vendor.notes = notes
        if tags is not None:
            vendor.tags = tags
        log.info("vendor.updated", vendor_id=str(vendor.id), name=name)

    await db.flush()
    return vendor


async def get_vendor(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    vendor_id: uuid.UUID,
) -> Optional[Vendor]:
    result = await db.execute(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def list_vendors(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Vendor]:
    query = select(Vendor).where(Vendor.workspace_id == workspace_id)
    if category:
        query = query.where(Vendor.category == category)
    query = query.order_by(Vendor.name).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_vendor(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    vendor_id: uuid.UUID,
) -> bool:
    vendor = await get_vendor(db, workspace_id, vendor_id)
    if vendor is None:
        return False
    await db.delete(vendor)
    log.info("vendor.deleted", vendor_id=str(vendor_id))
    return True
