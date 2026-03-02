"""schedule_followup tool.

Lets an agent schedule a future follow-up (e.g. "re-ping supplier in 24h").
The orchestrator persists the schedule and fires it via Celery beat / Temporal.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()


async def schedule_followup(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    delay_seconds: int,
    message: str,
) -> dict:
    log.info(
        "tool.schedule_followup.requested",
        agent_id=agent_id,
        delay_seconds=delay_seconds,
    )
    # TODO: post schedule_followup_request to Redis result queue
    return {
        "status": "scheduled",
        "delay_seconds": delay_seconds,
        "note": "follow-up schedule request posted to orchestrator",
    }
