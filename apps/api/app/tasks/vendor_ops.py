"""
Vendor operations — Celery tasks that process upsert requests posted
by agent containers via the orchestrator queue.

Agents cannot reach Postgres directly (agent-net isolation).
They post upsert_vendor_request events to the orchestrator queue;
this task executes the actual DB write with proper error handling.
"""
from __future__ import annotations

import asyncio
import uuid
import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.vendor_ops.handle_vendor_upsert",
    queue="orchestrator",
)
def handle_vendor_upsert(request: dict) -> dict:
    """
    Process a vendor upsert request posted by an agent tool.

    Expected keys: workspace_id, name, and any optional vendor fields
    (email, category, contact_name, phone, website, country, notes, tags).
    """
    log.info(
        "vendor_ops.upsert.received",
        workspace_id=request.get("workspace_id"),
        name=request.get("name"),
    )
    return asyncio.run(_do_upsert(request))


async def _do_upsert(request: dict) -> dict:
    """Inner async logic — importable without Celery for unit tests."""
    workspace_id_raw = request.get("workspace_id")
    name = request.get("name")

    if not workspace_id_raw or not name:
        log.warning("vendor_ops.upsert.invalid_payload", request=request)
        return {"success": False, "error": "workspace_id and name are required"}

    try:
        workspace_id = uuid.UUID(str(workspace_id_raw))
    except ValueError:
        log.warning("vendor_ops.upsert.invalid_workspace_id", workspace_id=workspace_id_raw)
        return {"success": False, "error": f"Invalid workspace_id: {workspace_id_raw}"}

    from app.db.session import make_session_factory
    from app.services.vendors import upsert_vendor

    async with make_session_factory()() as db:
        vendor = await upsert_vendor(
            db,
            workspace_id=workspace_id,
            name=name,
            email=request.get("email"),
            category=request.get("category"),
            contact_name=request.get("contact_name"),
            phone=request.get("phone"),
            website=request.get("website"),
            country=request.get("country"),
            notes=request.get("notes"),
            tags=request.get("tags"),
        )
        await db.commit()

    log.info("vendor_ops.upsert.done", vendor_id=str(vendor.id), name=name)
    return {"success": True, "vendor_id": str(vendor.id), "name": name}
