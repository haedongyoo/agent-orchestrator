"""request_approval tool.

The agent uses this to ask the user's permission for sensitive actions.
Creates a pending Approval row via the orchestrator Celery queue.
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

    Posts to the orchestrator queue — the orchestrator creates an Approval row,
    sets the task status to needs_approval, and notifies the user.
    """
    log.info(
        "tool.request_approval.requested",
        agent_id=agent_id,
        approval_type=approval_type,
        reason=reason,
    )

    from celery import current_app as celery_app

    celery_app.send_task(
        "app.tasks.approval_handler.handle_approval_request",
        kwargs={
            "agent_id": agent_id,
            "workspace_id": workspace_id,
            "thread_id": thread_id,
            "approval_type": approval_type,
            "scope": scope,
            "reason": reason,
        },
        queue="orchestrator",
    )

    return {
        "status": "pending",
        "approval_type": approval_type,
        "note": "approval request submitted — task paused until user decides",
    }
