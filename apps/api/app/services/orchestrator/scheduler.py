"""
Scheduler — manages follow-up triggers and periodic retries.

MVP: Celery beat tasks stored in Redis.
Production: Temporal workflows (recommended for long-running negotiations).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


class Scheduler:
    async def schedule_followup(
        self,
        task_id: uuid.UUID,
        when: datetime,
        payload: dict[str, Any],
    ) -> str:
        """
        Schedule a follow-up action for a task at a specific time.

        Returns a schedule_id for later cancellation.
        MVP: enqueue a Celery ETA task.
        """
        # TODO: implement Celery ETA or Temporal workflow timer
        schedule_id = f"followup-{task_id}-{int(when.timestamp())}"
        return schedule_id

    async def cancel_followup(self, schedule_id: str) -> bool:
        """Cancel a scheduled follow-up. Returns True if successfully cancelled."""
        # TODO: revoke Celery task or cancel Temporal timer
        return False
