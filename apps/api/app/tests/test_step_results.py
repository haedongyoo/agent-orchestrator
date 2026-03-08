"""
Tests for step_results — verifies WebSocket broadcast via Redis pub/sub.

Covers:
  - publish_event called with new_message after agent response
  - publish_event called with task_status when task completes
  - No publish when agent_text is empty and no error
  - publish_event not called when task has no thread_id
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_step(step_id, task_id, agent_id, status="running"):
    step = MagicMock()
    step.id = step_id
    step.task_id = task_id
    step.agent_id = agent_id
    step.status = status
    step.result = None
    return step


def _make_task(task_id, thread_id, status="running"):
    task = MagicMock()
    task.id = task_id
    task.thread_id = thread_id
    task.status = status
    return task


def _make_message(thread_id):
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.thread_id = thread_id
    msg.created_at = datetime.now(timezone.utc)
    return msg


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestStepResultsBroadcast:
    @pytest.mark.asyncio
    async def test_publishes_new_message_on_agent_response(self):
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        step = _make_step(step_id, task_id, agent_id)
        task = _make_task(task_id, thread_id)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(agent_id),
            "success": True,
            "output": {"text": "Hello from agent!"},
        }

        mock_db = AsyncMock()
        # Return step, then all_steps, then task from sequential execute calls
        step_result_mock = MagicMock()
        step_result_mock.scalar_one_or_none.return_value = step

        all_steps_mock = MagicMock()
        all_steps_mock.scalars.return_value.all.return_value = [step]

        task_result_mock = MagicMock()
        task_result_mock.scalar_one_or_none.return_value = task

        mock_db.execute = AsyncMock(side_effect=[
            step_result_mock, all_steps_mock, task_result_mock,
        ])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.db.session.make_session_factory", return_value=mock_session_factory), \
             patch("app.tasks.step_results.publish_event") as mock_publish:
            from app.tasks.step_results import _handle
            await _handle(result)

        # Should publish new_message event
        calls = mock_publish.call_args_list
        assert len(calls) >= 1
        new_msg_call = calls[0]
        assert new_msg_call[0][0] == thread_id
        event = new_msg_call[0][1]
        assert event["type"] == "new_message"
        assert event["data"]["content"] == "Hello from agent!"
        assert event["data"]["sender_type"] == "agent"

    @pytest.mark.asyncio
    async def test_publishes_task_status_on_completion(self):
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        step = _make_step(step_id, task_id, agent_id)
        task = _make_task(task_id, thread_id)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(agent_id),
            "success": True,
            "output": {"text": "Done!"},
        }

        mock_db = AsyncMock()
        step_result_mock = MagicMock()
        step_result_mock.scalar_one_or_none.return_value = step

        all_steps_mock = MagicMock()
        all_steps_mock.scalars.return_value.all.return_value = [step]

        task_result_mock = MagicMock()
        task_result_mock.scalar_one_or_none.return_value = task

        mock_db.execute = AsyncMock(side_effect=[
            step_result_mock, all_steps_mock, task_result_mock,
        ])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.db.session.make_session_factory", return_value=mock_session_factory), \
             patch("app.tasks.step_results.publish_event") as mock_publish:
            from app.tasks.step_results import _handle
            await _handle(result)

        # Should publish both new_message AND task_status
        calls = mock_publish.call_args_list
        assert len(calls) == 2
        task_status_call = calls[1]
        event = task_status_call[0][1]
        assert event["type"] == "task_status"
        assert event["data"]["task_id"] == str(task_id)
        assert event["data"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_no_publish_when_no_thread(self):
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        step = _make_step(step_id, task_id, agent_id)
        task = _make_task(task_id, thread_id=None)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(agent_id),
            "success": True,
            "output": {"text": "response"},
        }

        mock_db = AsyncMock()
        step_result_mock = MagicMock()
        step_result_mock.scalar_one_or_none.return_value = step

        all_steps_mock = MagicMock()
        all_steps_mock.scalars.return_value.all.return_value = [step]

        task_result_mock = MagicMock()
        task_result_mock.scalar_one_or_none.return_value = task

        mock_db.execute = AsyncMock(side_effect=[
            step_result_mock, all_steps_mock, task_result_mock,
        ])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.db.session.make_session_factory", return_value=mock_session_factory), \
             patch("app.tasks.step_results.publish_event") as mock_publish:
            from app.tasks.step_results import _handle
            await _handle(result)

        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_error_message(self):
        step_id = uuid.uuid4()
        task_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        step = _make_step(step_id, task_id, agent_id)
        task = _make_task(task_id, thread_id)

        result = {
            "step_id": str(step_id),
            "task_id": str(task_id),
            "agent_id": str(agent_id),
            "success": False,
            "output": {},
            "error": "LLM timeout",
        }

        mock_db = AsyncMock()
        step_result_mock = MagicMock()
        step_result_mock.scalar_one_or_none.return_value = step

        all_steps_mock = MagicMock()
        all_steps_mock.scalars.return_value.all.return_value = [step]

        task_result_mock = MagicMock()
        task_result_mock.scalar_one_or_none.return_value = task

        mock_db.execute = AsyncMock(side_effect=[
            step_result_mock, all_steps_mock, task_result_mock,
        ])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.db.session.make_session_factory", return_value=mock_session_factory), \
             patch("app.tasks.step_results.publish_event") as mock_publish:
            from app.tasks.step_results import _handle
            await _handle(result)

        calls = mock_publish.call_args_list
        assert len(calls) >= 1
        event = calls[0][0][1]
        assert event["type"] == "new_message"
        assert "[Agent error: LLM timeout]" in event["data"]["content"]


class TestPubSubPublish:
    def test_publish_event_calls_redis(self):
        thread_id = uuid.uuid4()
        event = {"type": "new_message", "data": {"content": "test"}}

        mock_redis = MagicMock()
        with patch("app.services.pubsub.sync_redis.Redis.from_url", return_value=mock_redis):
            from app.services.pubsub import publish_event
            publish_event(thread_id, event)

        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        assert str(thread_id) in channel
        mock_redis.close.assert_called_once()
