"""send_email / read_email_inbox tools.

Credentials are NEVER stored in this container. The orchestrator injects
a credentials_ref token; we resolve it via the VAULT_ADDR env var.
"""
from __future__ import annotations
import os
import structlog

log = structlog.get_logger()

RESULT_QUEUE_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


async def send_email(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    to: list[str],
    subject: str,
    body: str,
    attachments: list[dict] | None = None,
) -> dict:
    """
    Send an outbound email.
    The actual SMTP credentials are resolved server-side by the orchestrator
    after this tool posts a send_email_request event to the result queue.

    Agents never hold credentials — they request the action and the
    orchestrator/API executes it with proper creds + audit logging.
    """
    # TODO: post a send_email_request to Redis result queue
    # The orchestrator picks this up, validates against policy, then sends.
    log.info("tool.send_email.requested", agent_id=agent_id, to=to, subject=subject)
    return {
        "status": "queued",
        "to": to,
        "subject": subject,
        "note": "send_email request posted to orchestrator queue",
    }


async def read_email_inbox(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
) -> dict:
    """
    Request the latest emails for this thread from the orchestrator.
    Messages are pre-fetched and cached in Redis by the orchestrator's IMAP poller.
    """
    # TODO: read from Redis cache key: inbox:{workspace_id}:{thread_id}
    log.info("tool.read_email_inbox.requested", agent_id=agent_id, thread_id=thread_id)
    return {"messages": [], "note": "inbox read — IMAP poller not yet implemented"}
