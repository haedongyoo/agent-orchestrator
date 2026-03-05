"""
Orchestrator Router — the single message routing hub.

ALL message routing goes through route(). No connector or agent bypasses this.
Enforces policy before delivering any message.

Step dispatch:
  dispatch_step()         — create a new TaskStep + push to agent queue
  enqueue_existing_step() — push an already-persisted step to the agent queue
  _enqueue_to_agent()     — raw Celery send_task (lazy import, easy to mock)

Agent queue name: "agent.{agent_id}"
Celery task name: "agent.run_step"
"""
from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy import select
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
        task_id: Optional[uuid.UUID],
        workspace_id: uuid.UUID,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        Route a message from sender to receiver through the policy engine.

        When receiver_type == "agent" and the route is allowed and a task_id is
        provided, a TaskStep is created and dispatched to the agent's Redis queue.

        Returns:
          {
            "delivered":    bool,
            "blocked_by":   str | None,
            "approval_id":  UUID | None,
            "step_id":      str | None,   # set when a step was dispatched
          }
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
                "step_id": None,
            }

        # When sending to an agent with an active task, create + enqueue a step
        step_id: Optional[uuid.UUID] = None
        if receiver_type == "agent" and task_id is not None:
            step_id = await self.dispatch_step(
                task_id=task_id,
                agent_id=uuid.UUID(receiver_id),
                step_type="message",
                content=content,
                metadata=metadata,
                workspace_id=workspace_id,
                thread_id=thread_id,
            )

        return {
            "delivered": True,
            "blocked_by": None,
            "approval_id": None,
            "step_id": str(step_id) if step_id else None,
        }

    async def dispatch_step(
        self,
        *,
        task_id: uuid.UUID,
        agent_id: uuid.UUID,
        step_type: str,
        content: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        workspace_id: uuid.UUID,
        thread_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """
        Create a TaskStep record and push it to the agent container's Redis queue.

        Loads the agent's role_prompt and allowed_tools from DB, and the thread's
        message history, to build the full payload the agent runtime expects.

        Returns the new step's UUID.
        """
        from app.models.task import TaskStep

        tool_call = None
        if content is not None:
            tool_call = {"content": content, "metadata": metadata or {}}

        # Explicitly generate id so it is available before DB flush (mirrors
        # the pattern used in _create_approval_request).
        step_id = uuid.uuid4()
        step = TaskStep(
            id=step_id,
            task_id=task_id,
            agent_id=agent_id,
            step_type=step_type,
            tool_call=tool_call,
            status="queued",
        )
        self.db.add(step)
        await self.db.flush()

        # Load agent context (role_prompt, allowed_tools) from DB
        agent = await self._load_agent(agent_id)
        role_prompt = agent.role_prompt if agent else ""
        allowed_tools = agent.allowed_tools if agent else []

        # Load thread history for context
        thread_history: List[dict] = []
        if thread_id:
            thread_history = await self._load_thread_history(thread_id)

        self._enqueue_to_agent(
            agent_id=agent_id,
            step_id=step_id,
            task_id=task_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            role_prompt=role_prompt,
            allowed_tools=allowed_tools,
            thread_history=thread_history,
            payload=step.tool_call or {},
        )

        return step_id

    async def enqueue_existing_step(
        self,
        step: Any,  # TaskStep — typed loosely to avoid circular import
        workspace_id: uuid.UUID,
        thread_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Push an already-persisted TaskStep to the agent's Redis queue."""
        # Load agent context
        agent = await self._load_agent(step.agent_id)
        role_prompt = agent.role_prompt if agent else ""
        allowed_tools = agent.allowed_tools if agent else []

        # Load thread history
        thread_history: List[dict] = []
        if thread_id:
            thread_history = await self._load_thread_history(thread_id)

        self._enqueue_to_agent(
            agent_id=step.agent_id,
            step_id=step.id,
            task_id=step.task_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            role_prompt=role_prompt,
            allowed_tools=allowed_tools,
            thread_history=thread_history,
            payload=step.tool_call or {},
        )

    async def _load_agent(self, agent_id: uuid.UUID) -> Any:
        """Load agent from DB for role_prompt and allowed_tools."""
        from app.models.agent import Agent
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def _load_thread_history(
        self,
        thread_id: uuid.UUID,
        limit: int = 50,
    ) -> List[dict]:
        """
        Load recent messages for a thread, formatted as OpenAI-style message dicts.

        Returns [{"role": "user"|"assistant", "content": "..."}] ordered oldest-first.
        """
        from app.models.message import Message

        result = await self.db.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()

        history: List[dict] = []
        for msg in reversed(messages):  # oldest-first
            if msg.sender_type in ("user", "external"):
                role = "user"
            else:
                role = "assistant"
            history.append({"role": role, "content": msg.content})
        return history

    def _enqueue_to_agent(
        self,
        *,
        agent_id: uuid.UUID,
        step_id: uuid.UUID,
        task_id: uuid.UUID,
        workspace_id: uuid.UUID,
        thread_id: Optional[uuid.UUID],
        role_prompt: str,
        allowed_tools: list,
        thread_history: list,
        payload: dict,
    ) -> None:
        """
        Push a step payload to the agent container's Celery queue.

        Celery is imported lazily so unit tests can mock this method without
        needing a running broker.

        Sends as args=[payload_dict] — the agent runtime expects a single
        positional dict argument matching TaskStepPayload fields.
        """
        from app.worker import celery_app

        celery_app.send_task(
            "agent.run_step",
            args=[{
                "step_id": str(step_id),
                "task_id": str(task_id),
                "agent_id": str(agent_id),
                "workspace_id": str(workspace_id),
                "thread_id": str(thread_id) if thread_id else "",
                "role_prompt": role_prompt,
                "allowed_tools": allowed_tools,
                "thread_history": thread_history,
                "tool_call": payload,
            }],
            queue=f"agent.{agent_id}",
        )

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
