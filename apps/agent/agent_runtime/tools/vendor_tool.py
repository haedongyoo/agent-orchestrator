"""upsert_vendor tool.

Agents use this to record vendor/contractor contact info discovered during
negotiations. Data is persisted by the orchestrator via the result queue.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()


async def upsert_vendor(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    name: str,
    email: str | None = None,
    category: str | None = None,
    notes: str | None = None,
) -> dict:
    log.info("tool.upsert_vendor.requested", agent_id=agent_id, vendor_name=name)
    # TODO: post upsert_vendor_request to Redis result queue
    return {
        "status": "queued",
        "vendor_name": name,
        "note": "vendor upsert request posted to orchestrator",
    }
