from __future__ import annotations
"""
Agent CRUD endpoint tests.

Coverage:
  - POST   /api/workspaces/{id}/agents            (create: success, validation, auth)
  - GET    /api/workspaces/{id}/agents            (list: success, empty, wrong owner)
  - PUT    /api/workspaces/{id}/agents/{aid}      (update: success, partial, not found)
  - DELETE /api/workspaces/{id}/agents/{aid}      (delete: success, not found)

Container management endpoints (/container/start|stop) are excluded — they require
Docker and are tested separately in the container integration suite.

All DB calls are intercepted via AsyncMock — no real DB required.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.agent import Agent
from app.models.workspace import User, Workspace
from app.routers.agents import router as agents_router
from app.services.auth import create_access_token, get_current_user

# Minimal app — agents router only (no ContainerManager import path triggered)
app = FastAPI()
app.include_router(agents_router, prefix="/api/workspaces")


# ── Factories ──────────────────────────────────────────────────────────────────

def make_user(user_id: Optional[uuid.UUID] = None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="owner@example.com",
        password_hash="hashed",
        is_active=True,
    )


def make_workspace(workspace_id: Optional[uuid.UUID] = None, user_id: Optional[uuid.UUID] = None) -> Workspace:
    uid = user_id or uuid.uuid4()
    return Workspace(
        id=workspace_id or uuid.uuid4(),
        user_id=uid,
        name="Test Workspace",
        timezone="UTC",
        language_pref="en",
    )


def make_agent(workspace_id: uuid.UUID, agent_id: Optional[uuid.UUID] = None) -> Agent:
    return Agent(
        id=agent_id or uuid.uuid4(),
        workspace_id=workspace_id,
        name="Negotiator",
        role_prompt="You negotiate furniture supplier contracts.",
        allowed_tools=["send_email", "send_telegram"],
        is_enabled=True,
        rate_limit_per_min=10,
        max_concurrency=3,
    )


def make_mock_db(scalar_result=None, scalars_result=None):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    result.scalars.return_value.all.return_value = scalars_result or []
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def override_auth(user: User):
    async def _dep():
        return user
    return _dep


def override_db(db):
    async def _dep():
        yield db
    return _dep


# ── POST /api/workspaces/{id}/agents ──────────────────────────────────────────

class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_create_success(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        agent_id = uuid.uuid4()

        # First execute: workspace lookup
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        db = AsyncMock()
        db.execute = AsyncMock(return_value=ws_result)
        db.add = MagicMock()
        db.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = agent_id
            obj.is_enabled = True

        db.refresh = AsyncMock(side_effect=_refresh)
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{ws.id}/agents",
                    json={
                        "name": "Negotiator",
                        "role_prompt": "You negotiate supplier contracts.",
                        "allowed_tools": ["send_email"],
                        "rate_limit_per_min": 5,
                        "max_concurrency": 2,
                    },
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["name"] == "Negotiator"
            assert data["allowed_tools"] == ["send_email"]
            assert data["is_enabled"] is True
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_invalid_tool_rejected(self):
        """Unknown tool name → 422."""
        user = make_user()
        ws = make_workspace(user_id=user.id)

        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        db = AsyncMock()
        db.execute = AsyncMock(return_value=ws_result)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{ws.id}/agents",
                    json={
                        "name": "Bad Agent",
                        "role_prompt": "Do bad things.",
                        "allowed_tools": ["rm_rf", "curl_anything"],
                    },
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_empty_name_rejected(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        db = make_mock_db(scalar_result=ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{ws.id}/agents",
                    json={"name": "", "role_prompt": "x"},
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_workspace_not_found(self):
        user = make_user()
        db = make_mock_db(scalar_result=None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{uuid.uuid4()}/agents",
                    json={"name": "X", "role_prompt": "Y"},
                )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_unauthenticated(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/workspaces/{uuid.uuid4()}/agents",
                json={"name": "X", "role_prompt": "Y"},
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── GET /api/workspaces/{id}/agents ───────────────────────────────────────────

class TestListAgents:
    @pytest.mark.asyncio
    async def test_list_success(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        agents = [make_agent(ws.id), make_agent(ws.id)]

        # Two execute calls: workspace lookup, then agents query
        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = agents
        db.execute = AsyncMock(side_effect=[ws_result, agents_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/api/workspaces/{ws.id}/agents")
            assert resp.status_code == status.HTTP_200_OK
            assert len(resp.json()) == 2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_empty(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[ws_result, empty_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/api/workspaces/{ws.id}/agents")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_workspace_not_found(self):
        user = make_user()
        db = make_mock_db(scalar_result=None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/api/workspaces/{uuid.uuid4()}/agents")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()


# ── PUT /api/workspaces/{id}/agents/{aid} ─────────────────────────────────────

class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_update_name_and_prompt(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        agent = make_agent(ws.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        db.execute = AsyncMock(side_effect=[ws_result, agent_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}/agents/{agent.id}",
                    json={"name": "Updated Name", "role_prompt": "New prompt."},
                )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["name"] == "Updated Name"
            assert data["role_prompt"] == "New prompt."
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_toggle_enabled(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        agent = make_agent(ws.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        db.execute = AsyncMock(side_effect=[ws_result, agent_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}/agents/{agent.id}",
                    json={"is_enabled": False},
                )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["is_enabled"] is False
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_agent_not_found(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[ws_result, not_found])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}/agents/{uuid.uuid4()}",
                    json={"name": "X"},
                )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_invalid_tool_rejected(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        agent = make_agent(ws.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        db.execute = AsyncMock(side_effect=[ws_result, agent_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}/agents/{agent.id}",
                    json={"allowed_tools": ["hack_the_planet"]},
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()


# ── DELETE /api/workspaces/{id}/agents/{aid} ──────────────────────────────────

class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_delete_success(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        agent = make_agent(ws.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent
        db.execute = AsyncMock(side_effect=[ws_result, agent_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.delete(f"/api/workspaces/{ws.id}/agents/{agent.id}")
            assert resp.status_code == status.HTTP_204_NO_CONTENT
            db.delete.assert_called_once_with(agent)
            db.commit.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[ws_result, not_found])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.delete = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.delete(f"/api/workspaces/{ws.id}/agents/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_unauthenticated(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/workspaces/{uuid.uuid4()}/agents/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
