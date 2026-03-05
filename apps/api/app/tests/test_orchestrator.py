"""
Tests for the Orchestrator Router.

Verifies that:
  - All messages pass through policy before delivery
  - Audit logs are always written
  - Blocked routes return delivery=False + approval_id
  - Agent routes with a task_id create a TaskStep and enqueue it
  - dispatch_step() creates a TaskStep record + calls _enqueue_to_agent
  - _enqueue_to_agent sends correct task name and payload format
  - enqueue_existing_step loads agent context and thread history
  - _load_thread_history returns correct format
"""
from __future__ import annotations

import sys
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
        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue, \
             patch.object(orch, "_load_agent", AsyncMock(return_value=None)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[])):
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
        thread_id = uuid.uuid4()

        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue, \
             patch.object(orch, "_load_agent", AsyncMock(return_value=None)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[])):
            await orch.dispatch_step(
                task_id=task_id,
                agent_id=agent_id,
                step_type="plan",
                workspace_id=workspace_id,
                thread_id=thread_id,
            )

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["agent_id"] == agent_id
        assert call_kwargs["task_id"] == task_id
        assert call_kwargs["workspace_id"] == workspace_id
        assert call_kwargs["thread_id"] == thread_id

    @pytest.mark.asyncio
    async def test_dispatch_step_returns_step_id(self, orch):
        """dispatch_step returns a UUID that can be used to track the step."""
        with patch.object(orch, "_enqueue_to_agent"), \
             patch.object(orch, "_load_agent", AsyncMock(return_value=None)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[])):
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

        with patch.object(orch, "_enqueue_to_agent"), \
             patch.object(orch, "_load_agent", AsyncMock(return_value=None)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[])):
            await orch.dispatch_step(
                task_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                step_type="plan",
                workspace_id=uuid.uuid4(),
                # content intentionally omitted
            )

        assert added_steps, "No TaskStep was added"
        assert added_steps[0].tool_call is None

    @pytest.mark.asyncio
    async def test_dispatch_step_includes_role_prompt_and_tools(self, orch):
        """dispatch_step loads agent context and includes it in the payload."""
        agent_id = uuid.uuid4()
        mock_agent = MagicMock()
        mock_agent.role_prompt = "You are a negotiator"
        mock_agent.allowed_tools = ["send_email", "upsert_vendor"]

        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue, \
             patch.object(orch, "_load_agent", AsyncMock(return_value=mock_agent)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[{"role": "user", "content": "hi"}])):
            await orch.dispatch_step(
                task_id=uuid.uuid4(),
                agent_id=agent_id,
                step_type="message",
                content="negotiate",
                workspace_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
            )

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["role_prompt"] == "You are a negotiator"
        assert call_kwargs["allowed_tools"] == ["send_email", "upsert_vendor"]
        assert call_kwargs["thread_history"] == [{"role": "user", "content": "hi"}]

    @pytest.mark.asyncio
    async def test_dispatch_step_no_agent_uses_defaults(self, orch):
        """dispatch_step falls back to empty role_prompt and tools when agent not found."""
        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue, \
             patch.object(orch, "_load_agent", AsyncMock(return_value=None)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[])):
            await orch.dispatch_step(
                task_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                step_type="plan",
                workspace_id=uuid.uuid4(),
            )

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["role_prompt"] == ""
        assert call_kwargs["allowed_tools"] == []


# ── enqueue_existing_step() tests ─────────────────────────────────────────────

class TestEnqueueExistingStep:
    @pytest.mark.asyncio
    async def test_enqueue_existing_step_calls_enqueue(self, orch):
        """enqueue_existing_step passes step attributes to _enqueue_to_agent."""
        step = MagicMock()
        step.agent_id = uuid.uuid4()
        step.id = uuid.uuid4()
        step.task_id = uuid.uuid4()
        step.tool_call = {"content": "hello"}
        workspace_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        mock_agent = MagicMock()
        mock_agent.role_prompt = "You are a negotiator"
        mock_agent.allowed_tools = ["send_email"]

        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue, \
             patch.object(orch, "_load_agent", AsyncMock(return_value=mock_agent)), \
             patch.object(orch, "_load_thread_history", AsyncMock(return_value=[])):
            await orch.enqueue_existing_step(step, workspace_id=workspace_id, thread_id=thread_id)

        mock_enqueue.assert_called_once_with(
            agent_id=step.agent_id,
            step_id=step.id,
            task_id=step.task_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            role_prompt="You are a negotiator",
            allowed_tools=["send_email"],
            thread_history=[],
            payload={"content": "hello"},
        )

    @pytest.mark.asyncio
    async def test_enqueue_existing_step_no_thread_id(self, orch):
        """enqueue_existing_step works without thread_id."""
        step = MagicMock()
        step.agent_id = uuid.uuid4()
        step.id = uuid.uuid4()
        step.task_id = uuid.uuid4()
        step.tool_call = None
        workspace_id = uuid.uuid4()

        with patch.object(orch, "_enqueue_to_agent") as mock_enqueue, \
             patch.object(orch, "_load_agent", AsyncMock(return_value=None)):
            await orch.enqueue_existing_step(step, workspace_id=workspace_id)

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["thread_id"] is None
        assert call_kwargs["thread_history"] == []


# ── _enqueue_to_agent() tests ─────────────────────────────────────────────────

class TestEnqueueToAgent:
    def test_enqueue_uses_correct_task_name(self, orch):
        """_enqueue_to_agent sends task name 'agent.run_step' (not 'agent_runtime.tasks.run_step')."""
        agent_id = uuid.uuid4()
        mock_celery = MagicMock()
        mock_worker = MagicMock(celery_app=mock_celery)

        with patch.dict(sys.modules, {"app.worker": mock_worker}):
            orch._enqueue_to_agent(
                agent_id=agent_id,
                step_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                role_prompt="test prompt",
                allowed_tools=["send_email"],
                thread_history=[],
                payload={},
            )

        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "agent.run_step"
        assert call_args.kwargs["queue"] == f"agent.{agent_id}"

    def test_enqueue_sends_args_not_kwargs(self, orch):
        """_enqueue_to_agent sends payload as args=[dict] not kwargs={}."""
        mock_celery = MagicMock()
        mock_worker = MagicMock(celery_app=mock_celery)

        with patch.dict(sys.modules, {"app.worker": mock_worker}):
            orch._enqueue_to_agent(
                agent_id=uuid.uuid4(),
                step_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                role_prompt="prompt",
                allowed_tools=["send_email"],
                thread_history=[{"role": "user", "content": "hi"}],
                payload={"content": "hello"},
            )

        call_args = mock_celery.send_task.call_args
        # Should use args=, not kwargs=
        args_list = call_args.kwargs.get("args")
        assert args_list is not None, "Should use args= parameter"
        assert len(args_list) == 1
        payload_dict = args_list[0]
        assert "role_prompt" in payload_dict
        assert "allowed_tools" in payload_dict
        assert "thread_history" in payload_dict
        assert payload_dict["role_prompt"] == "prompt"
        assert payload_dict["allowed_tools"] == ["send_email"]
        assert payload_dict["thread_history"] == [{"role": "user", "content": "hi"}]

    def test_enqueue_payload_includes_all_required_fields(self, orch):
        """Verify the payload dict has all fields expected by TaskStepPayload."""
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        mock_celery = MagicMock()
        mock_worker = MagicMock(celery_app=mock_celery)

        with patch.dict(sys.modules, {"app.worker": mock_worker}):
            orch._enqueue_to_agent(
                agent_id=agent_id,
                step_id=step_id,
                task_id=task_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                role_prompt="You are a sourcing agent",
                allowed_tools=["send_email", "upsert_vendor"],
                thread_history=[{"role": "user", "content": "find suppliers"}],
                payload={"content": "search", "metadata": {}},
            )

        payload = mock_celery.send_task.call_args.kwargs["args"][0]
        assert payload["step_id"] == str(step_id)
        assert payload["task_id"] == str(task_id)
        assert payload["agent_id"] == str(agent_id)
        assert payload["workspace_id"] == str(workspace_id)
        assert payload["thread_id"] == str(thread_id)
        assert payload["role_prompt"] == "You are a sourcing agent"
        assert payload["allowed_tools"] == ["send_email", "upsert_vendor"]
        assert payload["thread_history"] == [{"role": "user", "content": "find suppliers"}]
        assert payload["tool_call"] == {"content": "search", "metadata": {}}


# ── _load_thread_history() tests ──────────────────────────────────────────────

class TestLoadThreadHistory:
    @pytest.mark.asyncio
    async def test_load_thread_history_maps_sender_types(self, orch, mock_db):
        """user and external messages become role=user, agent/system become role=assistant."""
        thread_id = uuid.uuid4()

        msg1 = MagicMock()
        msg1.sender_type = "user"
        msg1.content = "Hello"
        msg1.created_at = "2024-01-01T00:00:00"

        msg2 = MagicMock()
        msg2.sender_type = "agent"
        msg2.content = "Hi there"
        msg2.created_at = "2024-01-01T00:00:01"

        msg3 = MagicMock()
        msg3.sender_type = "external"
        msg3.content = "I'm a vendor"
        msg3.created_at = "2024-01-01T00:00:02"

        # Mock returns messages in DESC order (newest first)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [msg3, msg2, msg1]
        mock_db.execute = AsyncMock(return_value=mock_result)

        history = await orch._load_thread_history(thread_id)

        # Should be reversed to oldest-first
        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there"}
        assert history[2] == {"role": "user", "content": "I'm a vendor"}

    @pytest.mark.asyncio
    async def test_load_thread_history_empty(self, orch, mock_db):
        """Empty thread returns empty list."""
        thread_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        history = await orch._load_thread_history(thread_id)
        assert history == []
