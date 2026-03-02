"""
Orchestrator Celery Worker.

Handles:
  - Receiving task step results from agent-worker containers (via Redis)
  - Persisting results to Postgres
  - Dispatching follow-up steps
  - Scheduling IMAP inbox polls (beat tasks)
  - Broadcasting WebSocket events after DB writes

Queue: "orchestrator"
Agent queues: "agent.<agent_id>" (dispatched to agent-net containers)
"""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "orchestrator",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.step_results",   # process results coming back from agents
        "app.tasks.inbox_poll",     # periodic IMAP polling
        "app.tasks.followups",      # scheduled follow-up dispatching
        "app.tasks.vendor_ops",     # vendor/contractor CRM upserts from agents
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        # Check all agent container statuses every 30 seconds
        "monitor-containers": {
            "task": "app.tasks.container_monitor.refresh_all_containers",
            "schedule": 30.0,
        },
        # Poll shared email inboxes every 2 minutes
        "poll-inboxes": {
            "task": "app.tasks.inbox_poll.poll_all_inboxes",
            "schedule": 120.0,
        },
    },
)
