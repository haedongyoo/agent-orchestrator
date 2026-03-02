"""upsert_vendor tool.

Agents use this to record vendor/contractor contact info discovered during
negotiations. Data is persisted by the orchestrator via the result queue.

ARCHITECTURE NOTE:
  Agents cannot reach Postgres (agent-net isolation). This tool posts a
  vendor upsert request to the orchestrator queue via Celery send_task().
  The orchestrator's handle_vendor_upsert task executes the DB write.
"""
from __future__ import annotations

import os
from typing import Optional

import structlog

log = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Module-level Celery producer — lazy-initialized, reused across calls.
_orch_producer = None


def _get_producer():
    """Return a Celery app configured as a producer for the orchestrator queue."""
    global _orch_producer
    if _orch_producer is None:
        from celery import Celery
        _orch_producer = Celery(broker=REDIS_URL)
        _orch_producer.conf.update(
            task_serializer="json",
            accept_content=["json"],
        )
    return _orch_producer


async def upsert_vendor(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    name: str,
    email: Optional[str] = None,
    category: Optional[str] = None,
    contact_name: Optional[str] = None,
    phone: Optional[str] = None,
    website: Optional[str] = None,
    country: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """
    Post a vendor upsert request to the orchestrator queue.
    The orchestrator writes to Postgres; agents never hold DB credentials.
    """
    log.info("tool.upsert_vendor.requested", agent_id=agent_id, vendor_name=name)

    payload = {
        "workspace_id": workspace_id,
        "name": name,
        "email": email,
        "category": category,
        "contact_name": contact_name,
        "phone": phone,
        "website": website,
        "country": country,
        "notes": notes,
        "tags": tags,
        "_meta": {"agent_id": agent_id, "thread_id": thread_id},
    }

    _get_producer().send_task(
        "app.tasks.vendor_ops.handle_vendor_upsert",
        args=[payload],
        queue="orchestrator",
    )

    log.info("tool.upsert_vendor.queued", agent_id=agent_id, vendor_name=name)
    return {
        "status": "queued",
        "vendor_name": name,
        "note": "vendor upsert request posted to orchestrator",
    }
