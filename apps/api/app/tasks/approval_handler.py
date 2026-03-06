"""
Approval handler — Celery task that processes approval requests posted
by agent containers via the orchestrator queue.

Agents cannot reach Postgres directly (agent-net isolation).
They post request_approval events to the orchestrator queue;
this task creates the Approval row and sets the task to needs_approval.
"""
from __future__ import annotations

import asyncio
import uuid
import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.approval_handler.handle_approval_request",
    queue="orchestrator",
)
def handle_approval_request(request: dict) -> dict:
    """
    Process an approval request posted by an agent tool.

    Expected keys: workspace_id, agent_id, thread_id, approval_type, scope, reason
    """
    log.info(
        "approval_handler.received",
        workspace_id=request.get("workspace_id"),
        approval_type=request.get("approval_type"),
    )
    return asyncio.run(_do_create(request))


async def _do_create(request: dict) -> dict:
    """Inner async logic — importable without Celery for unit tests."""
    workspace_id_raw = request.get("workspace_id")
    agent_id_raw = request.get("agent_id")
    approval_type = request.get("approval_type")

    if not workspace_id_raw or not approval_type:
        log.warning("approval_handler.invalid_payload", request=request)
        return {"success": False, "error": "workspace_id and approval_type are required"}

    try:
        workspace_id = uuid.UUID(str(workspace_id_raw))
        agent_id = uuid.UUID(str(agent_id_raw)) if agent_id_raw else None
    except ValueError as e:
        return {"success": False, "error": f"Invalid UUID: {e}"}

    thread_id_raw = request.get("thread_id")
    thread_id = uuid.UUID(str(thread_id_raw)) if thread_id_raw else None

    from app.db.session import AsyncSessionLocal
    from app.models.approval import Approval

    async with AsyncSessionLocal() as db:
        approval = Approval(
            workspace_id=workspace_id,
            approval_type=approval_type,
            requested_by=agent_id,
            scope=request.get("scope", {}),
            status="pending",
            thread_id=thread_id,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

    log.info(
        "approval_handler.created",
        approval_id=str(approval.id),
        approval_type=approval_type,
    )
    return {"success": True, "approval_id": str(approval.id), "status": "pending"}
