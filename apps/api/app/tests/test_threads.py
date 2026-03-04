from __future__ import annotations
"""
Thread + Message CRUD endpoint tests.

Coverage:
  POST   /api/workspaces/{id}/threads              (create: success, validation, auth)
  GET    /api/threads/{id}                         (get: success, not found, wrong owner)
  POST   /api/threads/{id}/messages               (post message: success, validation)
  GET    /api/threads/{id}/messages?cursor=&limit= (list: success, empty, cursor pagination)

All DB calls intercepted via AsyncMock — no real DB required.
"""
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.message import Message
from app.models.thread import Thread
from app.models.workspace import User, Workspace
from app.routers.threads import router as threads_router
from app.services.auth import create_access_token, get_current_user

app = FastAPI()
app.include_router(threads_router, prefix="/api")


# ── Factories ──────────────────────────────────────────────────────────────────

def make_user(user_id: Optional[uuid.UUID] = None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
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


def make_thread(workspace_id: uuid.UUID, thread_id: Optional[uuid.UUID] = None) -> Thread:
    return Thread(
        id=thread_id or uuid.uuid4(),
        workspace_id=workspace_id,
        title="Supplier Negotiation",
        status="open",
    )


def make_message(thread_id: uuid.UUID, created_at: Optional[datetime] = None) -> Message:
    return Message(
        id=uuid.uuid4(),
        thread_id=thread_id,
        sender_type="user",
        sender_id=uuid.uuid4(),
        channel="web",
        content="Hello agent",
        metadata_={},
        created_at=created_at or datetime.now(timezone.utc),
    )


def mock_db_single(result):
    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = result
    db.execute = AsyncMock(return_value=r)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def mock_db_sequence(*results):
    """Return a db mock whose execute() returns each result in order."""
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


# ── POST /api/workspaces/{id}/threads ─────────────────────────────────────────

class TestCreateThread:
    @pytest.mark.asyncio
    async def test_create_success(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread_id = uuid.uuid4()

        db = mock_db_sequence(ws)

        async def _refresh(obj):
            obj.id = thread_id
            obj.status = "open"

        db.refresh.side_effect = _refresh

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/workspaces/{ws.id}/threads",
                    json={"title": "Supplier Negotiation"},
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["title"] == "Supplier Negotiation"
            assert data["status"] == "open"
            assert data["workspace_id"] == str(ws.id)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_empty_title_rejected(self):
        user = make_user()
        ws = make_workspace(user.id)
        db = mock_db_single(ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(f"/api/workspaces/{ws.id}/threads", json={"title": ""})
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_workspace_not_found(self):
        user = make_user()
        db = mock_db_single(None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/workspaces/{uuid.uuid4()}/threads",
                    json={"title": "Test"},
                )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_unauthenticated(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/workspaces/{uuid.uuid4()}/threads",
                json={"title": "Test"},
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── GET /api/threads/{id} ──────────────────────────────────────────────────────

class TestGetThread:
    @pytest.mark.asyncio
    async def test_get_success(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)

        # Two lookups: thread first, then workspace ownership check
        db = mock_db_sequence(thread, ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{thread.id}")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["title"] == thread.title
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_thread_not_found(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)

        # Thread lookup returns None
        db = mock_db_sequence(thread, None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_wrong_owner_returns_404(self):
        """Thread belongs to different workspace → workspace lookup by user fails → 404."""
        user = make_user()
        db = mock_db_sequence(None)  # workspace not found for this user

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()


# ── POST /api/threads/{id}/messages ───────────────────────────────────────────

class TestPostMessage:
    @pytest.mark.asyncio
    async def test_post_message_success(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)
        msg_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        db = mock_db_sequence(thread, ws)

        async def _refresh(obj):
            obj.id = msg_id
            obj.created_at = now

        db.refresh.side_effect = _refresh

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/threads/{thread.id}/messages",
                    json={"content": "Hello agent", "channel": "web"},
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["content"] == "Hello agent"
            assert data["sender_type"] == "user"
            assert data["channel"] == "web"
            assert data["thread_id"] == str(thread.id)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_message_empty_content_rejected(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)
        db = mock_db_sequence(thread, ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/threads/{thread.id}/messages",
                    json={"content": ""},
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_message_invalid_channel_rejected(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)
        db = mock_db_sequence(thread, ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/threads/{thread.id}/messages",
                    json={"content": "Hello", "channel": "fax"},
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_message_thread_not_found(self):
        user = make_user()
        db = mock_db_single(None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/threads/{uuid.uuid4()}/messages",
                    json={"content": "Hello"},
                )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_message_unauthenticated(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/threads/{uuid.uuid4()}/messages",
                json={"content": "Hello"},
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── GET /api/threads/{id}/messages ────────────────────────────────────────────

class TestListMessages:
    @pytest.mark.asyncio
    async def test_list_success(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)
        msgs = [make_message(thread.id), make_message(thread.id)]

        db = mock_db_sequence(thread, ws, msgs)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{thread.id}/messages")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert len(data["items"]) == 2
            assert "next_cursor" in data
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_empty(self):
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)

        db = mock_db_sequence(thread, ws, [])

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{thread.id}/messages")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["items"] == []
            assert data["next_cursor"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_next_cursor_set_when_full_page(self):
        """When items == limit, next_cursor is set to the last item's cursor."""
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)
        msgs = [make_message(thread.id) for _ in range(2)]

        db = mock_db_sequence(thread, ws, msgs)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{thread.id}/messages?limit=2")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["next_cursor"] is not None
            # cursor is base64-decodable JSON with created_at and id
            raw = base64.urlsafe_b64decode(data["next_cursor"] + "==")
            decoded = json.loads(raw)
            assert "created_at" in decoded
            assert "id" in decoded
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_no_cursor_when_partial_page(self):
        """When items < limit, next_cursor is None (end of results)."""
        user = make_user()
        ws = make_workspace(user.id)
        thread = make_thread(ws.id)
        msgs = [make_message(thread.id)]  # 1 item, limit=50

        db = mock_db_sequence(thread, ws, msgs)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{thread.id}/messages?limit=50")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["next_cursor"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_thread_not_found(self):
        user = make_user()
        db = mock_db_single(None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/threads/{uuid.uuid4()}/messages")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()
