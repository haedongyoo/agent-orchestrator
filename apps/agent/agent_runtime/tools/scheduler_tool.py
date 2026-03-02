"""schedule_followup tool.

Lets an agent schedule a future follow-up (e.g. "re-ping supplier in 24h").
Posts a schedule request to the orchestrator queue; the orchestrator creates
a Celery ETA task that fires after the specified delay.

Agents never schedule Celery tasks directly — the orchestrator owns scheduling.
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
    global _orch_producer
    if _orch_producer is None:
        from celery import Celery
        _orch_producer = Celery(broker=REDIS_URL)
        _orch_producer.conf.update(
            task_serializer="json",
            accept_content=["json"],
        )
    return _orch_producer


async def schedule_followup(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    delay_seconds: int,
    message: str,
) -> dict:
    """
    Schedule a future follow-up step.

    Posts handle_schedule_request to the orchestrator queue.
    The orchestrator resolves the current task for this thread and schedules
    a Celery ETA task (fire_followup) that wakes up the agent after delay_seconds.
    """
    log.info(
        "tool.schedule_followup.requested",
        agent_id=agent_id,
        delay_seconds=delay_seconds,
    )

    payload = {
        "workspace_id": workspace_id,
        "thread_id":    thread_id,
        "agent_id":     agent_id,
        "delay_seconds": delay_seconds,
        "message":       message,
    }

    _get_producer().send_task(
        "app.tasks.followups.handle_schedule_request",
        args=[payload],
        queue="orchestrator",
    )

    log.info("tool.schedule_followup.queued", agent_id=agent_id, delay_seconds=delay_seconds)
    return {
        "status": "scheduled",
        "delay_seconds": delay_seconds,
        "note": "follow-up schedule request posted to orchestrator",
    }
