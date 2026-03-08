"""
Tests for the task trace endpoint: GET /api/tasks/{task_id}/trace

Coverage:
  - Trace returns task, steps with agent names, and audit logs
  - Step duration_ms is calculated for terminal steps
  - Total duration is calculated for completed tasks
  - Empty steps/audit_logs returned when none exist
  - 404 on unknown task
  - 404 on non-owned task
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.task import Task, TaskStep
from app.models.agent import Agent
from app.models.audit import AuditLog
from app.models.workspace import User, Workspace
from app.routers.tasks import router as tasks_router
from app.services.auth import create_access_token, get_current_user

app = FastAPI()
app.include_router(tasks_router, prefix="/api")


# ── Factories ────────────────────────────────────────────────────────────────

def make_user(user_id: Optional[uuid.UUID] = None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="owner@example.com",
        password_hash="hashed",
        is_active=True,
    )


def make_workspace(workspace_id: Optional[uuid.UUID] = None, user_id: Optional[uuid.UUID] = None) -> Workspace:
    return Workspace(
        id=workspace_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name="Test Workspace",
        timezone="UTC",
        language_pref="en",
    )


def make_task(
    task_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[uuid.UUID] = None,
    thread_id: Optional[uuid.UUID] = None,
    task_status: str = "done",
) -> Task:
    now = datetime.now(timezone.utc)
    t = Task(
        id=task_id or uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        thread_id=thread_id or uuid.uuid4(),
        objective="negotiate pricing",
        status=task_status,
        created_by=uuid.uuid4(),
    )
    t.created_at = now - timedelta(seconds=5)
    t.updated_at = now
    return t


def make_step(
    task_id: uuid.UUID,
    agent_id: uuid.UUID,
    step_status: str = "done",
    step_type: str = "action",
    step_id: Optional[uuid.UUID] = None,
) -> TaskStep:
    now = datetime.now(timezone.utc)
    s = TaskStep(
        id=step_id or uuid.uuid4(),
        task_id=task_id,
        agent_id=agent_id,
        step_type=step_type,
        status=step_status,
    )
    s.created_at = now - timedelta(seconds=3)
    s.updated_at = now
    s.tool_call = {"tool": "send_email", "args": {"to": "vendor@test.com"}}
    s.result = {"text": "Email sent successfully"}
    return s


def make_agent(agent_id: uuid.UUID, workspace_id: uuid.UUID) -> Agent:
    return Agent(
        id=agent_id,
        workspace_id=workspace_id,
        name="Negotiator Agent",
        role_prompt="You are a negotiator.",
        allowed_tools=["send_email"],
        is_enabled=True,
    )


def make_audit(workspace_id: uuid.UUID, task_id: uuid.UUID) -> AuditLog:
    return AuditLog(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        actor_type="agent",
        actor_id=uuid.uuid4(),
        action="send_email",
        target_type="task",
        target_id=task_id,
        detail={"to": "vendor@test.com"},
        created_at=datetime.now(timezone.utc),
    )


# ── Test helpers ─────────────────────────────────────────────────────────────

def _build_mock_db(
    task: Optional[Task] = None,
    workspace: Optional[Workspace] = None,
    steps_with_agents: Optional[list] = None,
    audits: Optional[list] = None,
):
    """Build a mock DB that returns correct results for sequential execute calls."""
    mock_db = AsyncMock()
    results = []

    # 1st call: select Task
    task_result = MagicMock()
    task_result.scalar_one_or_none.return_value = task
    results.append(task_result)

    # 2nd call: select Workspace (ownership check)
    ws_result = MagicMock()
    ws_result.scalar_one_or_none.return_value = workspace
    results.append(ws_result)

    if task and workspace:
        # 3rd call: select TaskStep join Agent
        steps_result = MagicMock()
        steps_result.all.return_value = steps_with_agents or []
        results.append(steps_result)

        # 4th call: select AuditLog
        audit_result = MagicMock()
        audit_scalars = MagicMock()
        audit_scalars.all.return_value = audits or []
        audit_result.scalars.return_value = audit_scalars
        results.append(audit_result)

    mock_db.execute = AsyncMock(side_effect=results)
    return mock_db


# ── Tests ────────────────────────────────────────────────────────────────────

class TestGetTaskTrace:
    @pytest.mark.asyncio
    async def test_trace_returns_full_timeline(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        task = make_task(workspace_id=ws.id)
        agent_id = uuid.uuid4()
        agent = make_agent(agent_id, ws.id)
        step = make_step(task.id, agent_id)
        audit = make_audit(ws.id, task.id)

        mock_db = _build_mock_db(
            task=task,
            workspace=ws,
            steps_with_agents=[(step, agent.name)],
            audits=[audit],
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/tasks/{task.id}/trace",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["task"]["id"] == str(task.id)
            assert data["task"]["status"] == "done"
            assert len(data["steps"]) == 1
            assert data["steps"][0]["agent_name"] == "Negotiator Agent"
            assert data["steps"][0]["duration_ms"] is not None
            assert data["steps"][0]["duration_ms"] > 0
            assert len(data["audit_logs"]) == 1
            assert data["audit_logs"][0]["action"] == "send_email"
            assert data["total_duration_ms"] is not None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trace_empty_steps_and_audits(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        task = make_task(workspace_id=ws.id, task_status="queued")

        mock_db = _build_mock_db(
            task=task,
            workspace=ws,
            steps_with_agents=[],
            audits=[],
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/tasks/{task.id}/trace",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["steps"] == []
            assert data["audit_logs"] == []
            assert data["total_duration_ms"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trace_404_unknown_task(self):
        user = make_user()

        mock_db = _build_mock_db(task=None, workspace=None)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/tasks/{uuid.uuid4()}/trace",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trace_404_wrong_owner(self):
        user = make_user()
        task = make_task()

        mock_db = _build_mock_db(task=task, workspace=None)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/tasks/{task.id}/trace",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trace_running_step_has_no_duration(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        task = make_task(workspace_id=ws.id, task_status="running")
        agent_id = uuid.uuid4()
        step = make_step(task.id, agent_id, step_status="running")

        mock_db = _build_mock_db(
            task=task,
            workspace=ws,
            steps_with_agents=[(step, "Sourcing Agent")],
            audits=[],
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/tasks/{task.id}/trace",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["steps"][0]["duration_ms"] is None
            assert data["total_duration_ms"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trace_multiple_steps_ordered(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        task = make_task(workspace_id=ws.id)
        agent_id = uuid.uuid4()

        step1 = make_step(task.id, agent_id, step_type="plan")
        step2 = make_step(task.id, agent_id, step_type="action")

        # Make step2 later than step1
        step2.created_at = step1.created_at + timedelta(seconds=1)
        step2.updated_at = step1.updated_at + timedelta(seconds=1)

        mock_db = _build_mock_db(
            task=task,
            workspace=ws,
            steps_with_agents=[(step1, "Agent A"), (step2, "Agent A")],
            audits=[],
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/tasks/{task.id}/trace",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["steps"]) == 2
            assert data["steps"][0]["step_type"] == "plan"
            assert data["steps"][1]["step_type"] == "action"
        finally:
            app.dependency_overrides.clear()
