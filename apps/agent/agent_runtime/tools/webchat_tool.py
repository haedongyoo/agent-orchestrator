"""post_web_message tool.

Posts a message to the web chat thread via the orchestrator result queue.
The orchestrator then persists it to DB and broadcasts via WebSocket.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()


async def post_web_message(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    text: str,
) -> dict:
    """Post a message to the web chat thread."""
    log.info("tool.post_web_message.requested", agent_id=agent_id, thread_id=thread_id)
    # TODO: post web_message_request to Redis result queue
    return {"status": "queued", "thread_id": thread_id}
