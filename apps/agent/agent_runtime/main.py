"""
Agent Worker Entry Point — Celery app for the agent-runtime container.

Each agent gets its own dedicated queue: agent.{agent_id}
The orchestrator dispatches task steps to the correct queue by agent_id.
Workers process one step at a time (concurrency=1) to maintain predictable
per-agent rate limits and avoid race conditions.

NETWORK ISOLATION: This process runs in a container on agent-net only.
It can reach Redis but NOT Postgres or the internal API.
"""
import os
import json
import asyncio
import structlog
from celery import Celery

from agent_runtime.runner import AgentRunner, TaskStepPayload

log = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
AGENT_ID   = os.getenv("AGENT_ID", "")

if not AGENT_ID:
    raise RuntimeError("AGENT_ID environment variable is required")

celery_app = Celery(
    "agent_runtime",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker
    task_acks_late=True,            # ack after completion, not on receipt
)


@celery_app.task(
    name="agent.run_step",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def run_step(self, payload_dict: dict) -> dict:
    """
    Execute a single task step.
    Receives a serialised TaskStepPayload from the orchestrator.
    Posts the StepResult back via the Celery result backend (Redis).
    """
    log.info("agent.step.received", step_id=payload_dict.get("step_id"))

    try:
        payload = TaskStepPayload(**payload_dict)
        runner = AgentRunner()
        result = asyncio.run(runner.run(payload))

        log.info(
            "agent.step.completed",
            step_id=result.step_id,
            success=result.success,
        )
        return {
            "step_id": result.step_id,
            "task_id": result.task_id,
            "agent_id": result.agent_id,
            "success": result.success,
            "output": result.output,
            "error": result.error,
        }

    except Exception as exc:
        log.error("agent.step.failed", error=str(exc))
        raise self.retry(exc=exc)
