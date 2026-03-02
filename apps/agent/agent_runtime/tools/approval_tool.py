"""request_approval tool.

The agent uses this to ask the user's permission for sensitive actions.
Creates a pending Approval row via the orchestrator result queue.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()


async def request_approval(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    approval_type: str,
    scope: dict,
    reason: str,
) -> dict:
    """
    Request user approval for a sensitive action.
    Suspends the current task step until the user approves or rejects.
    """
    log.info(
        "tool.request_approval.requested",
        agent_id=agent_id,
        approval_type=approval_type,
        reason=reason,
    )
    # TODO: post approval_request to Redis result queue
    # The orchestrator will create an Approval row, set task status to
    # needs_approval, and notify the user via WebSocket/Telegram.
    return {
        "status": "pending",
        "approval_type": approval_type,
        "note": "approval request submitted — task paused until user decides",
    }
