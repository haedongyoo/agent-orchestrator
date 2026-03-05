"""
Follow-ups — Celery tasks for scheduled agent follow-up actions.

Two tasks:
  handle_schedule_request  — posted by agent scheduler_tool; finds task context,
                              then enqueues fire_followup with ETA
  fire_followup            — fires when the ETA timer matures; creates a new
                              TaskStep and dispatches it to the agent queue

Flow:
  Agent calls schedule_followup(delay_seconds, message)
    → scheduler_tool posts handle_schedule_request to orchestrator queue
  orchestrator handle_schedule_request:
    → finds latest running task for (workspace_id, thread_id)
    → calls Scheduler.schedule_followup() → creates fire_followup ETA task
  ETA fires after delay_seconds:
    → fire_followup creates a new TaskStep (type=action)
    → dispatches to agent.{agent_id} Celery queue
    → agent wakes up with followup context
"""
from __future__ import annotations

import asyncio
import uuid
import structlog

from app.worker import celery_app

log = structlog.get_logger()


# ── handle_schedule_request ────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.followups.handle_schedule_request",
    queue="orchestrator",
)
def handle_schedule_request(request: dict) -> dict:
    """
    Process a schedule_followup_request from an agent tool.

    Expected keys: workspace_id, thread_id, agent_id, delay_seconds, message
    """
    log.info(
        "followup.schedule_request.received",
        workspace_id=request.get("workspace_id"),
        delay_seconds=request.get("delay_seconds"),
    )
    return asyncio.run(_do_schedule(request))


async def _do_schedule(request: dict) -> dict:
    """Inner async logic for handle_schedule_request — lazy imports for testability."""
    workspace_id_raw = request.get("workspace_id")
    thread_id_raw    = request.get("thread_id")
    agent_id_raw     = request.get("agent_id")
    delay_seconds    = request.get("delay_seconds")
    message          = request.get("message", "")

    if not all([workspace_id_raw, thread_id_raw, agent_id_raw, delay_seconds]):
        return {"success": False, "error": "workspace_id, thread_id, agent_id, delay_seconds required"}

    try:
        workspace_id = uuid.UUID(str(workspace_id_raw))
        thread_id    = uuid.UUID(str(thread_id_raw))
        agent_id     = uuid.UUID(str(agent_id_raw))
        delay_seconds = int(delay_seconds)
    except (ValueError, TypeError) as exc:
        return {"success": False, "error": f"Invalid field: {exc}"}

    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.task import Task
    from app.services.orchestrator.scheduler import Scheduler

    async with AsyncSessionLocal() as db:
        # Find the latest running task for this thread
        result = await db.execute(
            select(Task)
            .where(
                Task.workspace_id == workspace_id,
                Task.thread_id    == thread_id,
                Task.status.in_(["queued", "running"]),
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()

    if task is None:
        log.warning("followup.no_active_task", thread_id=str(thread_id))
        return {"success": False, "error": "No active task found for thread"}

    scheduler = Scheduler()
    schedule_id = await scheduler.schedule_followup(
        workspace_id=workspace_id,
        thread_id=thread_id,
        agent_id=agent_id,
        task_id=task.id,
        delay_seconds=delay_seconds,
        message=message,
    )

    return {"success": True, "schedule_id": schedule_id, "task_id": str(task.id)}


# ── fire_followup ──────────────────────────────────────────────────────────────

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
    log.info("followup.fired", task_id=task_id, agent_id=agent_id)
    asyncio.run(_dispatch_followup(task_id, agent_id, workspace_id, thread_id, message))


async def _dispatch_followup(
    task_id: str,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    message: str,
) -> None:
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.task import Task, TaskStep
    from app.services.orchestrator.router import OrchestratorRouter

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, uuid.UUID(task_id))
        if not task or task.status in ("done", "failed"):
            log.info("followup.task_closed", task_id=task_id)
            return

        # Create a new follow-up step for the agent
        step = TaskStep(
            id=uuid.uuid4(),
            task_id=uuid.UUID(task_id),
            agent_id=uuid.UUID(agent_id),
            step_type="action",
            tool_call={"followup_message": message},
            status="queued",
        )
        db.add(step)
        await db.flush()

        # Dispatch to agent's Celery queue
        orch = OrchestratorRouter(db)
        await orch.enqueue_existing_step(step, workspace_id=uuid.UUID(workspace_id), thread_id=uuid.UUID(thread_id))

        await db.commit()

    log.info(
        "followup.step_dispatched",
        step_id=str(step.id),
        task_id=task_id,
        agent_id=agent_id,
    )
