"""
Tests for the Orchestrator Router.

Verifies that:
  - All messages pass through policy before delivery
  - Audit logs are always written
  - Blocked routes return delivery=False + approval_id
  - Agent routes with a task_id create a TaskStep and enqueue it
  - dispatch_step() creates a TaskStep record + calls _enqueue_to_agent
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.orchestrator.router import OrchestratorRouter
from app.services.orchestrator.policy import PolicyDecision


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def orch(mock_db):
    return OrchestratorRouter(db=mock_db)


# ── route() tests ──────────────────────────────────────────────────────────────

class TestOrchestratorRoute:
    @pytest.mark.asyncio
    async def test_blocked_route_returns_not_delivered(self, orch):
        blocked = PolicyDecision(
            allowed=False, reason="a2a_not_approved", approval_id=uuid.uuid4()
        )
        with patch.object(orch.policy, "check_route", AsyncMock(return_value=blocked)):
            result = await orch.route(
                sender_type="agent",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=None,
                workspace_id=uuid.uuid4(),
                content="hello",
            )
        assert result["delivered"] is False
        assert result["blocked_by"] == "a2a_not_approved"
        assert result["step_id"] is None

    @pytest.mark.asyncio
    async def test_blocked_route_passes_approval_id(self, orch):
        approval_id = uuid.uuid4()
        blocked = PolicyDecision(
            allowed=False, reason="a2a_not_approved", approval_id=approval_id
        )
        with patch.object(orch.policy, "check_route", AsyncMock(return_value=blocked)):
            result = await orch.route(
                sender_type="agent",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=None,
                workspace_id=uuid.uuid4(),
                content="hello",
            )
        assert result["approval_id"] == approval_id

    @pytest.mark.asyncio
    async def test_allowed_route_writes_audit_log(self, orch, mock_db):
        allowed = PolicyDecision(allowed=True, reason="default_allow")
        with patch.object(orch.policy, "check_route", AsyncMock(return_value=allowed)):
            await orch.route(
                sender_type="user",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=None,
                workspace_id=uuid.uuid4(),
                content="start negotiation",
            )
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_allowed_agent_route_with_task_dispatches_step(self, orch):
        """user → agent with task_id: dispatch_step should be called."""
        allowed = PolicyDecision(allowed=True, reason="default_allow")
        task_id = uuid.uuid4()
        step_id = uuid.uuid4()

        with patch.object(orch.policy, "check_route", AsyncMock(return_value=allowed)), \
             patch.object(orch, "dispatch_step", AsyncMock(return_value=step_id)) as mock_dispatch:
            result = await orch.route(
                sender_type="user",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=task_id,
                workspace_id=uuid.uuid4(),
                content="start negotiation",
            )

        assert result["delivered"] is True
        assert result["step_id"] == str(step_id)
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_allowed_agent_route_without_task_no_step(self, orch):
        """user → agent without task_id: no step is dispatched."""
        allowed = PolicyDecision(allowed=True, reason="default_allow")

        with patch.object(orch.policy, "check_route", AsyncMock(return_value=allowed)), \
             patch.object(orch, "dispatch_step", AsyncMock()) as mock_dispatch:
            result = await orch.route(
                sender_type="user",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=None,  # no task
                workspace_id=uuid.uuid4(),
                content="hello",
            )

        assert result["delivered"] is True
        assert result["step_id"] is None
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_allowed_non_agent_route_no_step(self, orch):
        """user → external_email: no step is dispatched even with task_id."""
        allowed = PolicyDecision(allowed=True, reason="email_recipient_ok")

        with patch.object(orch.policy, "check_route", AsyncMock(return_value=allowed)), \
             patch.object(orch, "dispatch_step", AsyncMock()) as mock_dispatch:
            result = await orch.route(
                sender_type="agent",
                sender_id=uuid.uuid4(),
                receiver_type="external_email",
                receiver_id="vendor@example.com",
                thread_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                content="Hello, we'd like to request a quote.",
            )

        assert result["delivered"] is True
        mock_dispatch.assert_not_called()


# ── dispatch_step() tests ──────────────────────────────────────────────────────

class TestDispatchStep:
    @pytest.mark.asyncio
    async def test_dispatch_step_adds_task_step(self, orch, mock_db):
        """dispatch_step creates a TaskStep DB row."""
        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue:
            await orch.dispatch_step(
                task_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                step_type="message",
                content="negotiate pricing",
                workspace_id=uuid.uuid4(),
            )

        mock_db.add.assert_called()
        mock_enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_step_enqueues_to_correct_agent(self, orch):
        """dispatch_step passes the agent_id to _enqueue_to_agent."""
        agent_id = uuid.uuid4()
        task_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue:
            await orch.dispatch_step(
                task_id=task_id,
                agent_id=agent_id,
                step_type="plan",
                workspace_id=workspace_id,
            )

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["agent_id"] == agent_id
        assert call_kwargs["task_id"] == task_id
        assert call_kwargs["workspace_id"] == workspace_id

    @pytest.mark.asyncio
    async def test_dispatch_step_returns_step_id(self, orch):
        """dispatch_step returns a UUID that can be used to track the step."""
        with patch.object(orch, "_enqueue_to_agent"):
            step_id = await orch.dispatch_step(
                task_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                step_type="action",
                workspace_id=uuid.uuid4(),
            )

        assert isinstance(step_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_dispatch_step_no_content_sets_null_tool_call(self, orch, mock_db):
        """dispatch_step with no content sets tool_call=None on the step."""
        added_steps = []

        def capture_add(obj):
            from app.models.task import TaskStep
            if isinstance(obj, TaskStep):
                added_steps.append(obj)

        mock_db.add.side_effect = capture_add

        with patch.object(orch, "_enqueue_to_agent"):
            await orch.dispatch_step(
                task_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                step_type="plan",
                workspace_id=uuid.uuid4(),
                # content intentionally omitted
            )

        assert added_steps, "No TaskStep was added"
        assert added_steps[0].tool_call is None


# ── enqueue_existing_step() tests ─────────────────────────────────────────────

class TestEnqueueExistingStep:
    def test_enqueue_existing_step_calls_enqueue(self, orch):
        """enqueue_existing_step passes step attributes to _enqueue_to_agent."""
        step = MagicMock()
        step.agent_id = uuid.uuid4()
        step.id = uuid.uuid4()
        step.task_id = uuid.uuid4()
        step.tool_call = {"content": "hello"}
        workspace_id = uuid.uuid4()

        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue:
            orch.enqueue_existing_step(step, workspace_id=workspace_id)

        mock_enqueue.assert_called_once_with(
            agent_id=step.agent_id,
            step_id=step.id,
            task_id=step.task_id,
            workspace_id=workspace_id,
            payload={"content": "hello"},
        )
