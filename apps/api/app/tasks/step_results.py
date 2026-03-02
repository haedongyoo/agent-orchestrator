"""
Step Results — Celery tasks that process results posted by agent containers.

Agent containers post StepResult payloads to the "orchestrator" queue after
completing a task step. This module handles those results:
  1. Persist result to task_steps DB row
  2. Update task status
  3. Decide and enqueue the next step (via planner)
  4. Broadcast WebSocket event to UI
"""
from __future__ import annotations

import asyncio
import uuid
import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.step_results.handle_step_result",
    queue="orchestrator",
)
def handle_step_result(result: dict) -> None:
    """
    Process a StepResult dict posted by an agent container.

    Expected keys: step_id, task_id, agent_id, success, output, error
    """
    log.info(
        "step_results.received",
        step_id=result.get("step_id"),
        success=result.get("success"),
    )
    asyncio.run(_handle(result))


async def _handle(result: dict) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models.task import TaskStep, Task

    async with AsyncSessionLocal() as db:
        step = await db.get(TaskStep, uuid.UUID(result["step_id"]))
        if not step:
            log.warning("step_results.step_not_found", step_id=result["step_id"])
            return

        step.result = result.get("output")
        step.status = "done" if result.get("success") else "failed"

        # TODO: trigger planner to generate next steps if task is still running
        # TODO: broadcast task_status WebSocket event

        await db.commit()
        log.info("step_results.persisted", step_id=result["step_id"], status=step.status)
