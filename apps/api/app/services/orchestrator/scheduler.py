"""
Scheduler — manages follow-up triggers and periodic retries.

MVP: Celery ETA tasks stored in Redis (schedule_id = Celery async result ID).
     ETA tasks can be revoked via celery.control.revoke() before they fire.
Production: Temporal workflows (recommended for long-running negotiations).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

log = structlog.get_logger()


class Scheduler:
    async def schedule_followup(
        self,
        *,
        workspace_id: uuid.UUID,
        thread_id: uuid.UUID,
        agent_id: uuid.UUID,
        task_id: uuid.UUID,
        delay_seconds: int,
        message: str,
    ) -> str:
        """
        Schedule a follow-up action at (now + delay_seconds).

        Enqueues a Celery ETA task — when the timer fires, a new TaskStep is
        created and dispatched to the agent's queue.

        Returns a schedule_id (Celery async result ID) for later cancellation.
        """
        from app.worker import celery_app  # lazy — celery not installed locally

        eta = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

        result = celery_app.send_task(
            "app.tasks.followups.fire_followup",
            kwargs={
                "task_id": str(task_id),
                "agent_id": str(agent_id),
                "workspace_id": str(workspace_id),
                "thread_id": str(thread_id),
                "message": message,
            },
            eta=eta,
            queue="orchestrator",
        )

        schedule_id = result.id
        log.info(
            "scheduler.followup_scheduled",
            schedule_id=schedule_id,
            task_id=str(task_id),
            agent_id=str(agent_id),
            delay_seconds=delay_seconds,
            eta=eta.isoformat(),
        )
        return schedule_id

    async def cancel_followup(self, schedule_id: str) -> bool:
        """
        Cancel a scheduled follow-up before it fires.

        Uses celery.control.revoke() — works as long as the ETA task hasn't
        started yet (i.e. the Celery worker hasn't picked it up).
        Returns True always (revoke is fire-and-forget; no confirmation from worker).
        """
        from app.worker import celery_app  # lazy

        celery_app.control.revoke(schedule_id, terminate=False)
        log.info("scheduler.followup_cancelled", schedule_id=schedule_id)
        return True
