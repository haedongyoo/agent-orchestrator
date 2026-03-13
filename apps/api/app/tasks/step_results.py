"""
Step Results — Celery tasks that process results posted by agent containers.

Agent containers post StepResult payloads to the "orchestrator" queue after
completing a task step. This module handles those results:
  1. Persist result to task_steps DB row
  2. Update task status based on all steps' combined state
  3. Dispatch follow-up steps via planner (TODO: V1 — LLM-based next step)
  4. Broadcast WebSocket event to UI via Redis pub/sub

StepResult payload keys: step_id, task_id, agent_id, success, output, error
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import structlog

from app.worker import celery_app
from app.services.pubsub import publish_event

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
    from app.db.session import make_session_factory
    from app.models.task import TaskStep, Task
    from app.models.message import Message

    async with make_session_factory()() as db:
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

        # Save agent's response as a Message in the thread
        agent_text = ""
        agent_msg = None
        if task and task.thread_id:
            output = result.get("output", {})
            agent_text = output.get("text", "")
            is_truncated = output.get("truncated", False)

            if not agent_text and is_truncated:
                agent_text = (
                    "[Agent reached maximum iterations without a final response. "
                    "The model may need to be upgraded for better agent capabilities.]"
                )
            elif not agent_text and result.get("error"):
                agent_text = f"[Agent error: {result['error']}]"
            elif not agent_text and not result.get("success"):
                agent_text = "[Agent failed to generate a response.]"

            if agent_text:
                agent_msg = Message(
                    thread_id=task.thread_id,
                    sender_type="agent",
                    sender_id=step.agent_id,
                    channel="web",
                    content=agent_text,
                )
                db.add(agent_msg)
                log.info(
                    "step_results.message_created",
                    thread_id=str(task.thread_id),
                    agent_id=str(step.agent_id),
                    text_length=len(agent_text),
                )

        await db.commit()
        log.info("step_results.persisted", step_id=result["step_id"], status=step.status)

        # Broadcast events to WebSocket clients via Redis pub/sub
        if task and task.thread_id:
            if agent_text and agent_msg:
                created_at = agent_msg.created_at or datetime.now(timezone.utc)
                publish_event(task.thread_id, {
                    "type": "new_message",
                    "data": {
                        "id": str(agent_msg.id),
                        "thread_id": str(task.thread_id),
                        "sender_type": "agent",
                        "sender_id": str(step.agent_id),
                        "channel": "web",
                        "content": agent_text,
                        "created_at": created_at.isoformat(),
                    },
                })
            if all_terminal:
                publish_event(task.thread_id, {
                    "type": "task_status",
                    "data": {
                        "task_id": str(task.id),
                        "status": task.status,
                    },
                })
