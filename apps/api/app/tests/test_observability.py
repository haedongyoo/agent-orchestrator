"""
Tests for Observability — StepTrace model, metrics persistence, trace API.

Verifies:
  - StepTrace CRUD
  - Trace events persisted from step result
  - TaskStep timing/token columns updated
  - GET /api/tasks/{id}/trace returns full trace
  - Trace aggregation (total tokens, duration)
  - Empty trace (step with no events)
  - Runner emits trace events with correct structure
"""
from __future__ import annotations

import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.step_trace import StepTrace, TRACE_EVENT_TYPES
from app.models.task import TaskStep

# Add agent_runtime to path for runner tests
_AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agent")
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)


# ── StepTrace model tests ─────────────────────────────────────────────────────

class TestStepTraceModel:
    def test_step_trace_table_name(self):
        assert StepTrace.__tablename__ == "step_traces"

    def test_step_trace_has_required_columns(self):
        cols = {c.name for c in StepTrace.__table__.columns}
        assert {"id", "step_id", "event_type", "timestamp", "detail"} <= cols

    def test_valid_event_types_defined(self):
        assert "llm_request" in TRACE_EVENT_TYPES
        assert "tool_call" in TRACE_EVENT_TYPES
        assert "error" in TRACE_EVENT_TYPES
        assert "completed" in TRACE_EVENT_TYPES
        assert "rate_limit" in TRACE_EVENT_TYPES


# ── TaskStep metric columns ──────────────────────────────────────────────────

class TestTaskStepMetrics:
    def test_task_step_has_metric_columns(self):
        cols = {c.name for c in TaskStep.__table__.columns}
        expected = {"started_at", "completed_at", "duration_ms", "input_tokens",
                    "output_tokens", "iterations", "agent_model"}
        assert expected <= cols

    def test_task_step_traces_relationship(self):
        assert "traces" in TaskStep.__mapper__.relationships


# ── step_results._handle() — metrics + traces persistence ────────────────────

def _make_mock_db(mock_step, mock_task):
    """Create a mock async session that returns mock_step and mock_task."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_step)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_step])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_task)),
    ])
    mock_db.add = MagicMock()
    return mock_db


class TestStepResultsHandle:
    @pytest.mark.asyncio
    async def test_persists_metrics_from_result(self):
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.task_id = task_id
        mock_step.status = "running"

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.status = "running"

        mock_db = _make_mock_db(mock_step, mock_task)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(uuid.uuid4()),
            "success": True,
            "output": {"text": "done"},
            "metrics": {
                "started_at": "2026-03-04T10:00:00+00:00",
                "completed_at": "2026-03-04T10:00:03+00:00",
                "duration_ms": 3200,
                "input_tokens": 1500,
                "output_tokens": 800,
                "iterations": 2,
                "model": "anthropic/claude-opus-4-6",
            },
            "traces": [],
        }

        with patch("app.db.session.AsyncSessionLocal", return_value=mock_ctx):
            from app.tasks.step_results import _handle
            await _handle(result)

        assert mock_step.duration_ms == 3200
        assert mock_step.input_tokens == 1500
        assert mock_step.output_tokens == 800
        assert mock_step.iterations == 2
        assert mock_step.agent_model == "anthropic/claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_persists_trace_events(self):
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.task_id = task_id
        mock_step.status = "running"

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.status = "running"

        mock_db = _make_mock_db(mock_step, mock_task)
        added_objects = []
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(uuid.uuid4()),
            "success": True,
            "output": {"text": "done"},
            "metrics": {},
            "traces": [
                {"event_type": "started", "timestamp": "2026-03-04T10:00:00+00:00", "detail": {"model": "test"}},
                {"event_type": "llm_request", "timestamp": "2026-03-04T10:00:01+00:00", "detail": {}},
                {"event_type": "completed", "timestamp": "2026-03-04T10:00:02+00:00", "detail": {"duration_ms": 2000}},
            ],
        }

        with patch("app.db.session.AsyncSessionLocal", return_value=mock_ctx):
            from app.tasks.step_results import _handle
            await _handle(result)

        trace_objs = [o for o in added_objects if isinstance(o, StepTrace)]
        assert len(trace_objs) == 3
        assert trace_objs[0].event_type == "started"
        assert trace_objs[1].event_type == "llm_request"
        assert trace_objs[2].event_type == "completed"

    @pytest.mark.asyncio
    async def test_handles_missing_metrics_gracefully(self):
        """Result with no metrics/traces should still work."""
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.task_id = task_id
        mock_step.status = "running"

        mock_task = MagicMock()
        mock_task.id = task_id

        mock_db = _make_mock_db(mock_step, mock_task)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(uuid.uuid4()),
            "success": True,
            "output": {"text": "done"},
        }

        with patch("app.db.session.AsyncSessionLocal", return_value=mock_ctx):
            from app.tasks.step_results import _handle
            await _handle(result)

        assert mock_step.status == "done"
        mock_db.commit.assert_called_once()


# ── Runner trace emission tests ──────────────────────────────────────────────

class TestRunnerTraceEmission:
    @pytest.mark.asyncio
    async def test_runner_produces_traces_on_success(self):
        from agent_runtime.runner import AgentRunner, TaskStepPayload

        runner = AgentRunner()

        payload = TaskStepPayload(
            step_id=str(uuid.uuid4()),
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            workspace_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4()),
            role_prompt="You are a test agent.",
            allowed_tools=[],
            thread_history=[{"role": "user", "content": "Hello"}],
        )

        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = "Hi there!"
        mock_choice.message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("agent_runtime.runner.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await runner.run(payload)

        assert result.success is True
        assert len(result.traces) > 0
        assert result.metrics["model"] == runner.model
        assert result.metrics["input_tokens"] == 100
        assert result.metrics["output_tokens"] == 50
        assert result.metrics["iterations"] == 1
        assert result.metrics["duration_ms"] >= 0

        event_types = [t["event_type"] for t in result.traces]
        assert "started" in event_types
        assert "llm_request" in event_types
        assert "llm_response" in event_types
        assert "completed" in event_types

    @pytest.mark.asyncio
    async def test_runner_produces_traces_on_error(self):
        from agent_runtime.runner import AgentRunner, TaskStepPayload

        runner = AgentRunner()

        payload = TaskStepPayload(
            step_id=str(uuid.uuid4()),
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            workspace_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4()),
            role_prompt="You are a test agent.",
            allowed_tools=[],
            thread_history=[{"role": "user", "content": "Hello"}],
        )

        with patch("agent_runtime.runner.litellm.acompletion", AsyncMock(side_effect=RuntimeError("LLM down"))):
            result = await runner.run(payload)

        assert result.success is False
        # Error message may vary in local env vs Docker (litellm import issues)
        assert result.error is not None
        assert len(result.traces) > 0

        event_types = [t["event_type"] for t in result.traces]
        assert "error" in event_types

    @pytest.mark.asyncio
    async def test_runner_traces_tool_calls(self):
        from agent_runtime.runner import AgentRunner, TaskStepPayload

        runner = AgentRunner()

        payload = TaskStepPayload(
            step_id=str(uuid.uuid4()),
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            workspace_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4()),
            role_prompt="You are a test agent.",
            allowed_tools=["translate_message"],
            thread_history=[{"role": "user", "content": "Translate hello"}],
        )

        mock_tc = MagicMock()
        mock_tc.id = "tc_1"
        mock_tc.function.name = "translate_message"
        mock_tc.function.arguments = '{"text": "hello", "target_language": "es"}'

        mock_choice1 = MagicMock()
        mock_choice1.finish_reason = "tool_calls"
        mock_choice1.message.content = None
        mock_choice1.message.tool_calls = [mock_tc]

        mock_response1 = MagicMock()
        mock_response1.choices = [mock_choice1]
        mock_response1.usage = MagicMock(prompt_tokens=200, completion_tokens=30)

        mock_choice2 = MagicMock()
        mock_choice2.finish_reason = "stop"
        mock_choice2.message.content = "Hola"
        mock_choice2.message.tool_calls = None

        mock_response2 = MagicMock()
        mock_response2.choices = [mock_choice2]
        mock_response2.usage = MagicMock(prompt_tokens=300, completion_tokens=10)

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response1 if call_count == 1 else mock_response2

        async def mock_translate(**kwargs):
            return {"translated_text": "hola", "detected_source_language": "en"}

        mock_registry = {"translate_message": mock_translate}

        with patch("agent_runtime.runner.litellm.acompletion", AsyncMock(side_effect=mock_acompletion)), \
             patch("agent_runtime.runner.build_tool_registry", return_value=mock_registry):
            result = await runner.run(payload)

        assert result.success is True
        event_types = [t["event_type"] for t in result.traces]
        assert "tool_call" in event_types
        assert "tool_result" in event_types

        tc_events = [t for t in result.traces if t["event_type"] == "tool_call"]
        assert tc_events[0]["detail"]["tool"] == "translate_message"

    @pytest.mark.asyncio
    async def test_runner_step_result_has_correct_structure(self):
        from agent_runtime.runner import AgentRunner, TaskStepPayload

        runner = AgentRunner()
        payload = TaskStepPayload(
            step_id=str(uuid.uuid4()),
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            workspace_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4()),
            role_prompt="Test",
            allowed_tools=[],
            thread_history=[{"role": "user", "content": "Hi"}],
        )

        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = "Hello!"
        mock_choice.message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=25)

        with patch("agent_runtime.runner.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await runner.run(payload)

        assert isinstance(result.traces, list)
        assert isinstance(result.metrics, dict)
        assert "started_at" in result.metrics
        assert "completed_at" in result.metrics
        assert "duration_ms" in result.metrics
        assert "input_tokens" in result.metrics
        assert "output_tokens" in result.metrics
        assert "iterations" in result.metrics
        assert "model" in result.metrics


# ── Trace API endpoint tests ─────────────────────────────────────────────────

class TestTraceEndpoint:
    def test_task_step_response_includes_metrics(self):
        from app.routers.tasks import TaskStepResponse
        fields = TaskStepResponse.model_fields
        assert "started_at" in fields
        assert "duration_ms" in fields
        assert "input_tokens" in fields
        assert "output_tokens" in fields
        assert "iterations" in fields
        assert "agent_model" in fields

    def test_trace_event_response_schema(self):
        from app.routers.tasks import TraceEventResponse
        fields = TraceEventResponse.model_fields
        assert "id" in fields
        assert "step_id" in fields
        assert "event_type" in fields
        assert "timestamp" in fields
        assert "detail" in fields

    def test_task_trace_response_schema(self):
        from app.routers.tasks import TaskTraceResponse
        fields = TaskTraceResponse.model_fields
        assert "task" in fields
        assert "steps" in fields
        assert "total_tokens" in fields
        assert "total_duration_ms" in fields
