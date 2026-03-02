"""
Step Results — Celery tasks that process results posted by agent containers.

Agent containers post StepResult payloads to the "orchestrator" queue after
completing a task step. This module handles those results:
  1. Persist result to task_steps DB row
  2. Update task status based on all steps' combined state
  3. Dispatch follow-up steps via planner (TODO: V1 — LLM-based next step)
  4. Broadcast WebSocket event to UI (TODO: V1)

StepResult payload keys: step_id, task_id, agent_id, success, output, error
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
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.task import TaskStep, Task

    async with AsyncSessionLocal() as db:
        step_result = await db.execute(
            select(TaskStep).where(TaskStep.id == uuid.UUID(result["step_id"]))
        )
        step = step_result.scalar_one_or_none()
        if step is None:
            log.warning("step_results.step_not_found", step_id=result["step_id"])
            return

        step.result = result.get("output")
        step.status = "done" if result.get("success") else "failed"

        # Recalculate parent task status from all sibling steps
        all_steps_result = await db.execute(
            select(TaskStep).where(TaskStep.task_id == step.task_id)
        )
        all_steps = all_steps_result.scalars().all()

        # Apply the in-memory update to the current step before checking
        for s in all_steps:
            if s.id == step.id:
                s.status = step.status

        all_terminal = all(s.status in ("done", "failed") for s in all_steps)
        any_failed = any(s.status == "failed" for s in all_steps)

        task_result = await db.execute(
            select(Task).where(Task.id == step.task_id)
        )
        task = task_result.scalar_one_or_none()
        if task and all_terminal:
            task.status = "failed" if any_failed else "done"
            log.info(
                "step_results.task_status_updated",
                task_id=str(step.task_id),
                status=task.status,
            )

        # TODO: V1 — if task still running, trigger planner for next steps
        # TODO: V1 — broadcast task_status WebSocket event

        await db.commit()
        log.info("step_results.persisted", step_id=result["step_id"], status=step.status)
