"""
Tests for the Scheduler service and follow-up task pipeline.

Covers:
  - Scheduler.schedule_followup() — creates Celery ETA task, returns schedule_id
  - Scheduler.cancel_followup()   — calls celery.control.revoke()
  - _do_schedule()                — finds active task, delegates to Scheduler
  - _dispatch_followup()          — creates TaskStep, dispatches to agent queue
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock celery before importing anything that depends on it
_celery_mock = MagicMock()
sys.modules.setdefault("celery", _celery_mock)
sys.modules.setdefault("app.worker", MagicMock(celery_app=MagicMock()))

from app.services.orchestrator.scheduler import Scheduler  # noqa: E402
from app.tasks.followups import _do_schedule, _dispatch_followup  # noqa: E402


# ── Scheduler service tests ────────────────────────────────────────────────────

class TestSchedulerService:
    @pytest.mark.asyncio
    async def test_schedule_followup_returns_schedule_id(self):
        mock_result = MagicMock()
        mock_result.id = "celery-task-abc123"

        mock_celery = MagicMock()
        mock_celery.send_task.return_value = mock_result

        with patch("app.services.orchestrator.scheduler.celery_app", mock_celery, create=True):
            with patch("app.services.orchestrator.scheduler.Scheduler.schedule_followup") as mock_sched:
                mock_sched.return_value = "celery-task-abc123"
                scheduler = Scheduler()
                # Test via internal logic with mocked celery_app
                pass

        # Direct test: patch the lazy import inside schedule_followup
        import app.worker as worker_mod
        original_celery = getattr(worker_mod, "celery_app", None)

        mock_celery_app = MagicMock()
        mock_celery_app.send_task.return_value = MagicMock(id="celery-task-abc123")

        with patch.object(worker_mod, "celery_app", mock_celery_app):
            scheduler = Scheduler()
            schedule_id = await scheduler.schedule_followup(
                workspace_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                delay_seconds=3600,
                message="Follow up with supplier",
            )

        assert schedule_id == "celery-task-abc123"
        mock_celery_app.send_task.assert_called_once()
        call_kwargs = mock_celery_app.send_task.call_args
        assert call_kwargs[0][0] == "app.tasks.followups.fire_followup"
        assert call_kwargs[1]["queue"] == "orchestrator"
        assert call_kwargs[1]["eta"] is not None

    @pytest.mark.asyncio
    async def test_cancel_followup_calls_revoke(self):
        import app.worker as worker_mod
        mock_celery_app = MagicMock()
        mock_celery_app.control = MagicMock()

        with patch.object(worker_mod, "celery_app", mock_celery_app):
            scheduler = Scheduler()
            result = await scheduler.cancel_followup("some-schedule-id")

        assert result is True
        mock_celery_app.control.revoke.assert_called_once_with("some-schedule-id", terminate=False)

    @pytest.mark.asyncio
    async def test_schedule_sets_eta_in_future(self):
        import app.worker as worker_mod
        before = datetime.now(timezone.utc)

        mock_celery_app = MagicMock()
        mock_celery_app.send_task.return_value = MagicMock(id="sch-id")

        with patch.object(worker_mod, "celery_app", mock_celery_app):
            scheduler = Scheduler()
            await scheduler.schedule_followup(
                workspace_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                delay_seconds=60,
                message="Test",
            )

        mock_celery_app.send_task.assert_called_once()
        _, send_kwargs = mock_celery_app.send_task.call_args
        eta = send_kwargs["eta"]
        assert eta > before


# ── _do_schedule tests ─────────────────────────────────────────────────────────

class TestDoSchedule:
    @pytest.mark.asyncio
    async def test_missing_fields_returns_error(self):
        result = await _do_schedule({"workspace_id": str(uuid.uuid4())})
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_error(self):
        result = await _do_schedule({
            "workspace_id": "not-a-uuid",
            "thread_id": str(uuid.uuid4()),
            "agent_id": str(uuid.uuid4()),
            "delay_seconds": 60,
            "message": "test",
        })
        assert result["success"] is False
        assert "Invalid field" in result["error"]

    @pytest.mark.asyncio
    async def test_no_active_task_returns_error(self):
        ws_id  = str(uuid.uuid4())
        thr_id = str(uuid.uuid4())
        ag_id  = str(uuid.uuid4())

        mock_db = AsyncMock()
        no_task_result = MagicMock()
        no_task_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=no_task_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=MagicMock(return_value=mock_db))
        with patch("app.db.session.make_session_factory", mock_factory):
            result = await _do_schedule({
                "workspace_id": ws_id,
                "thread_id":    thr_id,
                "agent_id":     ag_id,
                "delay_seconds": 60,
                "message":       "Test",
            })

        assert result["success"] is False
        assert "No active task" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_request_schedules_followup(self):
        ws_id  = str(uuid.uuid4())
        thr_id = str(uuid.uuid4())
        ag_id  = str(uuid.uuid4())
        task_id = uuid.uuid4()

        mock_task = MagicMock()
        mock_task.id = task_id

        mock_db = AsyncMock()
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task
        mock_db.execute = AsyncMock(return_value=task_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        mock_scheduler = AsyncMock()
        mock_scheduler.schedule_followup = AsyncMock(return_value="sched-id-xyz")

        mock_factory = MagicMock(return_value=MagicMock(return_value=mock_db))
        with (
            patch("app.db.session.make_session_factory", mock_factory),
            patch("app.services.orchestrator.scheduler.Scheduler", return_value=mock_scheduler),
        ):
            result = await _do_schedule({
                "workspace_id": ws_id,
                "thread_id":    thr_id,
                "agent_id":     ag_id,
                "delay_seconds": 3600,
                "message":       "Follow up",
            })

        assert result["success"] is True
        assert result["schedule_id"] == "sched-id-xyz"
        assert result["task_id"] == str(task_id)


# ── _dispatch_followup tests ───────────────────────────────────────────────────

class TestDispatchFollowup:
    @pytest.mark.asyncio
    async def test_closed_task_does_not_create_step(self):
        task_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())

        closed_task = MagicMock()
        closed_task.status = "done"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=closed_task)
        mock_db.add = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=MagicMock(return_value=mock_db))
        with patch("app.db.session.make_session_factory", mock_factory):
            await _dispatch_followup(task_id, agent_id, workspace_id, thread_id, "Follow up")

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_task_creates_and_dispatches_step(self):
        task_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())

        active_task = MagicMock()
        active_task.status = "running"
        active_task.id = uuid.UUID(task_id)

        mock_orch = MagicMock()
        mock_orch.enqueue_existing_step = AsyncMock()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=active_task)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=MagicMock(return_value=mock_db))
        with (
            patch("app.db.session.make_session_factory", mock_factory),
            patch("app.services.orchestrator.router.OrchestratorRouter", return_value=mock_orch),
        ):
            await _dispatch_followup(task_id, agent_id, workspace_id, thread_id, "Follow up now")

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        mock_orch.enqueue_existing_step.assert_called_once()
        mock_db.commit.assert_awaited_once()
