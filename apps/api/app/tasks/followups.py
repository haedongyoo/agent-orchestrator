"""
Follow-ups — Celery tasks for scheduled agent follow-up actions.

When an agent calls schedule_followup(), the result queue handler creates
a Celery ETA task via this module. When the timer fires:
  1. Look up the task/thread context
  2. Dispatch a new task step to the agent's queue
  3. Log the trigger in audit_logs
"""
from __future__ import annotations

import asyncio
import uuid
import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.followups.fire_followup",
    queue="orchestrator",
)
def fire_followup(
    task_id: str,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    message: str,
) -> None:
    """
    Fire a scheduled follow-up step for an agent.
    Called by Celery when an ETA task matures.
    """
    log.info(
        "followup.fired",
        task_id=task_id,
        agent_id=agent_id,
    )
    asyncio.run(_dispatch_followup(task_id, agent_id, workspace_id, thread_id, message))


async def _dispatch_followup(
    task_id: str,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    message: str,
) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models.task import Task, TaskStep

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, uuid.UUID(task_id))
        if not task or task.status in ("done", "failed"):
            log.info("followup.task_closed", task_id=task_id)
            return

        # Create a new action step for the follow-up
        step = TaskStep(
            task_id=uuid.UUID(task_id),
            agent_id=uuid.UUID(agent_id),
            step_type="action",
            tool_call={"followup_message": message},
            status="queued",
        )
        db.add(step)
        await db.commit()

        # TODO: dispatch step to agent's Celery queue
        log.info("followup.step_created", step_id=str(step.id), task_id=task_id)
