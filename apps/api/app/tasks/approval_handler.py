"""
Approval Handler — Celery task that processes approval requests from agents.

When an agent calls request_approval(), it posts to this task via the
orchestrator queue. This task creates the Approval row and sets the
associated task status to needs_approval.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.tasks.approval_handler.handle_approval_request")
def handle_approval_request(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    approval_type: str,
    scope: dict,
    reason: str,
) -> dict:
    """Create an Approval row and set any active task to needs_approval."""
    log.info("approval_handler.start", agent_id=agent_id, approval_type=approval_type)
    result = asyncio.run(_handle(
        agent_id=agent_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        approval_type=approval_type,
        scope=scope,
        reason=reason,
    ))
    return result


async def _handle(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    approval_type: str,
    scope: dict,
    reason: str,
) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.models.approval import Approval
    from app.models.task import Task
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        approval_id = uuid.uuid4()
        approval = Approval(
            id=approval_id,
            workspace_id=uuid.UUID(workspace_id),
            thread_id=uuid.UUID(thread_id),
            approval_type=approval_type,
            requested_by=uuid.UUID(agent_id),
            scope=scope,
            reason=reason,
        )
        db.add(approval)

        # Find the active task for this thread and set to needs_approval
        result = await db.execute(
            select(Task).where(
                Task.thread_id == uuid.UUID(thread_id),
                Task.workspace_id == uuid.UUID(workspace_id),
                Task.status.in_(["queued", "running"]),
            )
        )
        task = result.scalar_one_or_none()
        if task is not None:
            task.status = "needs_approval"
            approval.task_id = task.id

        await db.commit()

    log.info("approval_handler.done", approval_id=str(approval_id))
    return {"approval_id": str(approval_id), "status": "pending"}
