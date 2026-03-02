"""
Orchestrator Router — the single message routing hub.

ALL message routing goes through route(). No connector or agent bypasses this.
Enforces policy before delivering any message.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestrator.policy import PolicyEngine, RouteRequest
from app.models.audit import AuditLog


class OrchestratorRouter:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.policy = PolicyEngine(db)

    async def route(
        self,
        *,
        sender_type: str,
        sender_id: uuid.UUID,
        receiver_type: str,
        receiver_id: str,
        thread_id: uuid.UUID,
        task_id: uuid.UUID | None,
        workspace_id: uuid.UUID,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """
        Route a message from sender to receiver.

        Returns:
          { "delivered": bool, "blocked_by": str|None, "approval_id": UUID|None }
        """
        req = RouteRequest(
            sender_type=sender_type,
            sender_id=sender_id,
            receiver_type=receiver_type,
            receiver_id=receiver_id,
            thread_id=thread_id,
            task_id=task_id,
            workspace_id=workspace_id,
            content_preview=content[:200],
        )

        decision = await self.policy.check_route(req)

        await self._audit(
            workspace_id=workspace_id,
            actor_type=sender_type,
            actor_id=sender_id,
            action=f"route_{'allowed' if decision.allowed else 'blocked'}",
            detail={
                "receiver_type": receiver_type,
                "receiver_id": receiver_id,
                "thread_id": str(thread_id),
                "reason": decision.reason,
            },
        )

        if not decision.allowed:
            return {
                "delivered": False,
                "blocked_by": decision.reason,
                "approval_id": decision.approval_id,
            }

        # TODO: dispatch to appropriate connector (email / telegram / web)
        return {"delivered": True, "blocked_by": None, "approval_id": None}

    async def _audit(self, *, workspace_id, actor_type, actor_id, action, detail):
        log = AuditLog(
            workspace_id=workspace_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            detail=detail,
        )
        self.db.add(log)
        await self.db.flush()
