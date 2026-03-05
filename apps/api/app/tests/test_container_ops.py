"""
Tests for container operations — Celery task dispatch and DB-based status reads.

Verifies that:
  - Start/stop endpoints dispatch Celery tasks (not call ContainerManager directly)
  - Get status reads from AgentContainer table (no Docker socket needed)
  - Disabled agent cannot be started
  - Stop endpoint returns 202 with "stopping" status
"""
from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.agent import Agent
from app.models.workspace import User, Workspace
from app.routers.agents import router as agents_router
from app.services.auth import get_current_user

app = FastAPI()
app.include_router(agents_router, prefix="/api")


# ── Factories ──────────────────────────────────────────────────────────────────

def make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash="hashed",
        is_active=True,
    )


def make_workspace(user_id: uuid.UUID) -> Workspace:
    return Workspace(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Test WS",
        timezone="UTC",
        language_pref="en",
    )


def make_agent(workspace_id: uuid.UUID, is_enabled: bool = True) -> Agent:
    return Agent(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="Test Agent",
        role_prompt="You are a test agent.",
        allowed_tools=["send_email"],
        is_enabled=is_enabled,
        rate_limit_per_min=10,
        max_concurrency=3,
    )


def override_auth(user: User):
    async def _dep():
        return user
    return _dep


def override_db(db):
    async def _dep():
        yield db
    return _dep


def mock_db_sequence(*results):
    db = AsyncMock()
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.scalars.return_value.all.return_value = r
        else:
            m.scalar_one_or_none.return_value = r
        mocks.append(m)
    db.execute = AsyncMock(side_effect=mocks)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestStartContainer:
    @pytest.mark.asyncio
    async def test_start_sends_celery_task(self):
        """Start endpoint dispatches Celery task, returns 202."""
        user = make_user()
        ws = make_workspace(user.id)
        agent = make_agent(ws.id, is_enabled=True)

        db = mock_db_sequence(ws, agent)
        mock_celery = MagicMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            with patch.dict(sys.modules, {"app.worker": MagicMock(celery_app=mock_celery)}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    resp = await c.post(
                        f"/api/{ws.id}/agents/{agent.id}/container/start"
                    )
            assert resp.status_code == status.HTTP_202_ACCEPTED
            data = resp.json()
            assert data["status"] == "starting"
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args
            assert call_args[0][0] == "app.tasks.container_ops.start_agent_container"
            assert call_args.kwargs["args"] == [str(agent.id)]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_start_disabled_agent_400(self):
        """Cannot start a disabled agent."""
        user = make_user()
        ws = make_workspace(user.id)
        agent = make_agent(ws.id, is_enabled=False)

        db = mock_db_sequence(ws, agent)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/{ws.id}/agents/{agent.id}/container/start"
                )
            assert resp.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()


class TestStopContainer:
    @pytest.mark.asyncio
    async def test_stop_sends_celery_task(self):
        """Stop endpoint dispatches Celery task, returns 202."""
        user = make_user()
        ws = make_workspace(user.id)
        agent = make_agent(ws.id)

        db = mock_db_sequence(ws, agent)
        mock_celery = MagicMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            with patch.dict(sys.modules, {"app.worker": MagicMock(celery_app=mock_celery)}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    resp = await c.post(
                        f"/api/{ws.id}/agents/{agent.id}/container/stop"
                    )
            assert resp.status_code == status.HTTP_202_ACCEPTED
            data = resp.json()
            assert data["status"] == "stopping"
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args
            assert call_args[0][0] == "app.tasks.container_ops.stop_agent_container"
        finally:
            app.dependency_overrides.clear()


class TestGetContainerStatus:
    @pytest.mark.asyncio
    async def test_get_status_reads_from_db(self):
        """GET status reads from AgentContainer table, no Docker socket."""
        user = make_user()
        ws = make_workspace(user.id)
        agent = make_agent(ws.id)

        mock_record = MagicMock()
        mock_record.status = "running"
        mock_record.container_id = "abc123"
        mock_record.container_name = f"openclaw-agent-{agent.id}"
        mock_record.image = "openclaw/agent-runtime:latest"
        mock_record.started_at = None
        mock_record.stopped_at = None
        mock_record.last_status_check_at = None
        mock_record.exit_code = None
        mock_record.restart_count = 0

        # ws lookup, agent lookup, container record lookup
        db = mock_db_sequence(ws, agent, mock_record)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(
                    f"/api/{ws.id}/agents/{agent.id}/container"
                )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["status"] == "running"
            assert data["container_id"] == "abc123"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_status_no_container(self):
        """GET status when no container exists returns no_container."""
        user = make_user()
        ws = make_workspace(user.id)
        agent = make_agent(ws.id)

        # ws, agent, container record = None
        db = mock_db_sequence(ws, agent, None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(
                    f"/api/{ws.id}/agents/{agent.id}/container"
                )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["status"] == "no_container"
        finally:
            app.dependency_overrides.clear()
