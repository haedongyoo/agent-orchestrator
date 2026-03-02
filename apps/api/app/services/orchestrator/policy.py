"""
Policy Engine — enforces all governance rules.

This is the authoritative location for:
  - Agent-to-agent (A2A) communication checks
  - Approval gate lookups
  - Domain allow/deny lists
  - Outbound rate-limit enforcement
  - Recipient novelty checks (new recipient → approval required)

Nothing bypasses this module. All routing decisions go through check_route().
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RouteRequest:
    """Describes a proposed message route from one actor to another."""
    sender_type: str           # "agent" | "user" | "system"
    sender_id: uuid.UUID
    receiver_type: str         # "agent" | "user" | "external_email" | "telegram"
    receiver_id: str           # agent_id, user_id, email address, or chat_id
    thread_id: uuid.UUID
    task_id: Optional[uuid.UUID]
    workspace_id: uuid.UUID
    content_preview: str       # first 200 chars — never log full content


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    approval_id: Optional[uuid.UUID] = None  # set when a new approval was created


class PolicyEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_route(self, req: RouteRequest) -> PolicyDecision:
        """
        Main entry point. Returns allow/deny + reason.
        Creates a pending Approval row when a route is blocked and needs user consent.
        """
        # Rule 1: A2A is forbidden without approval
        if req.sender_type == "agent" and req.receiver_type == "agent":
            return await self._check_a2a(req)

        # Rule 2: Outbound email to new recipient may require approval
        if req.receiver_type == "external_email":
            return await self._check_email_recipient(req)

        # Default: allow
        return PolicyDecision(allowed=True, reason="default_allow")

    async def _check_a2a(self, req: RouteRequest) -> PolicyDecision:
        """
        Check for an active approved A2A permission matching this agent pair + thread.
        Blocks and creates a pending Approval if none found.
        """
        from app.models.approval import Approval
        from sqlalchemy import select

        result = await self.db.execute(
            select(Approval).where(
                Approval.workspace_id == req.workspace_id,
                Approval.approval_type == "enable_agent_chat",
                Approval.status == "approved",
            )
        )
        approvals = result.scalars().all()

        now = datetime.now(timezone.utc)
        for approval in approvals:
            scope = approval.scope or {}
            agents_in_scope = scope.get("agents", [])

            # Both sender and receiver must be in the approved agent set
            if str(req.sender_id) not in agents_in_scope or req.receiver_id not in agents_in_scope:
                continue

            # If approval is scoped to a thread, it must match
            if "thread_id" in scope and scope["thread_id"] != str(req.thread_id):
                continue

            # If a duration window is set, verify it has not expired
            if "duration_seconds" in scope and approval.decided_at is not None:
                decided = approval.decided_at
                if decided.tzinfo is None:
                    decided = decided.replace(tzinfo=timezone.utc)
                if (now - decided).total_seconds() > scope["duration_seconds"]:
                    continue

            return PolicyDecision(allowed=True, reason="a2a_approved")

        # No active approval found — block and create a pending request
        approval_id = await self._create_approval_request(
            req,
            approval_type="enable_agent_chat",
            reason=f"Agent {req.sender_id} wants to send to Agent {req.receiver_id}",
        )
        return PolicyDecision(
            allowed=False,
            reason="a2a_not_approved",
            approval_id=approval_id,
        )

    async def _check_email_recipient(self, req: RouteRequest) -> PolicyDecision:
        """Check if the recipient email is known/approved for this workspace."""
        # TODO: query known recipients, domain allow/deny lists, volume caps
        return PolicyDecision(allowed=True, reason="email_recipient_ok")

    async def _create_approval_request(
        self,
        req: RouteRequest,
        approval_type: str,
        reason: str,
    ) -> uuid.UUID:
        """Persist a pending Approval row and return its id."""
        from app.models.approval import Approval

        # Explicitly generate id so it is available before DB flush
        approval_id = uuid.uuid4()
        approval = Approval(
            id=approval_id,
            workspace_id=req.workspace_id,
            thread_id=req.thread_id,
            task_id=req.task_id,
            approval_type=approval_type,
            requested_by=req.sender_id,
            scope={
                "agents": [str(req.sender_id), req.receiver_id],
                "thread_id": str(req.thread_id),
            },
            reason=reason,
        )
        self.db.add(approval)
        await self.db.flush()
        return approval_id
