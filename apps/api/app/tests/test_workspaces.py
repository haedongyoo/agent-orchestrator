from __future__ import annotations
"""
Workspace endpoint tests.

Coverage:
  - POST /api/workspaces          (success, validation errors)
  - GET  /api/workspaces/{id}     (success, not found, wrong owner)
  - PUT  /api/workspaces/{id}     (success, partial update, not found)
  - POST /api/workspaces/{id}/shared-email  (success, invalid provider)
  - PUT  /api/workspaces/{id}/shared-email/{eid} (success, not found)

All DB calls are intercepted via AsyncMock — no real DB connection needed.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.workspace import SharedEmailAccount, User, Workspace
from app.routers.workspaces import router as ws_router
from app.services.auth import create_access_token, get_current_user

# Minimal test app — only the workspace router
app = FastAPI()
app.include_router(ws_router, prefix="/api/workspaces")


# ── Fixtures ───────────────────────────────────────────────────────────────────

def make_user(user_id: uuid.UUID | None = None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="owner@example.com",
        password_hash="hashed",
        sso_provider=None,
        sso_sub=None,
        is_active=True,
    )


def make_workspace(workspace_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> Workspace:
    return Workspace(
        id=workspace_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name="Test Workspace",
        timezone="UTC",
        language_pref="en",
    )


def make_email_account(workspace_id: uuid.UUID) -> SharedEmailAccount:
    return SharedEmailAccount(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        provider_type="imap",
        credentials_ref="vault://email/1",
        from_alias="procurement@example.com",
        signature_template=None,
        is_active=True,
    )


def make_mock_db(scalar_result=None):
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def override_auth(user: User):
    """Return a dependency override that yields the given user."""
    async def _get_current_user_override():
        return user
    return _get_current_user_override


def override_db(db):
    async def _get_db_override():
        yield db
    return _get_db_override


def auth_headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


# ── POST /api/workspaces ───────────────────────────────────────────────────────

class TestCreateWorkspace:
    @pytest.mark.asyncio
    async def test_create_success(self):
        user = make_user()
        ws_id = uuid.uuid4()

        async def _refresh(obj):
            obj.id = ws_id

        db = make_mock_db()
        db.refresh.side_effect = _refresh

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/workspaces",
                    json={"name": "Acme HQ", "timezone": "America/New_York", "language_pref": "en"},
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["name"] == "Acme HQ"
            assert data["timezone"] == "America/New_York"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_defaults(self):
        """Timezone and language_pref default to UTC / en."""
        user = make_user()

        async def _refresh(obj):
            obj.id = uuid.uuid4()

        db = make_mock_db()
        db.refresh.side_effect = _refresh

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/api/workspaces", json={"name": "Minimal"})
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["timezone"] == "UTC"
            assert data["language_pref"] == "en"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_empty_name_rejected(self):
        """Empty name → 422."""
        user = make_user()
        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(make_mock_db())
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/api/workspaces", json={"name": ""})
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_unauthenticated(self):
        """No token → 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/workspaces", json={"name": "Test"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── GET /api/workspaces/{id} ───────────────────────────────────────────────────

class TestGetWorkspace:
    @pytest.mark.asyncio
    async def test_get_success(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        db = make_mock_db(scalar_result=ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/api/workspaces/{ws.id}")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["name"] == ws.name
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        """Workspace not in DB → 404."""
        user = make_user()
        db = make_mock_db(scalar_result=None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/api/workspaces/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_wrong_owner(self):
        """Workspace owned by different user → 404 (not 403, to avoid leaking existence)."""
        user = make_user()
        # DB returns nothing because the WHERE clause includes user_id
        db = make_mock_db(scalar_result=None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/api/workspaces/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()


# ── PUT /api/workspaces/{id} ───────────────────────────────────────────────────

class TestUpdateWorkspace:
    @pytest.mark.asyncio
    async def test_update_name(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        db = make_mock_db(scalar_result=ws)

        async def _refresh(obj):
            pass  # object already mutated in place

        db.refresh.side_effect = _refresh

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}",
                    json={"name": "New Name"},
                )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["name"] == "New Name"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_partial_only_timezone(self):
        """Sending only timezone leaves name and language_pref unchanged."""
        user = make_user()
        ws = make_workspace(user_id=user.id)
        original_name = ws.name
        db = make_mock_db(scalar_result=ws)
        db.refresh.side_effect = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}",
                    json={"timezone": "Asia/Seoul"},
                )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["timezone"] == "Asia/Seoul"
            assert data["name"] == original_name
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        user = make_user()
        db = make_mock_db(scalar_result=None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(f"/api/workspaces/{uuid.uuid4()}", json={"name": "X"})
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()


# ── POST /api/workspaces/{id}/shared-email ─────────────────────────────────────

class TestAddSharedEmail:
    @pytest.mark.asyncio
    async def test_add_email_success(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        acct = make_email_account(ws.id)

        # First execute → workspace lookup; refresh → email account id
        db = make_mock_db(scalar_result=ws)

        async def _refresh(obj):
            obj.id = acct.id
            obj.is_active = True

        db.refresh.side_effect = _refresh

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{ws.id}/shared-email",
                    json={
                        "provider_type": "imap",
                        "credentials_ref": "vault://email/42",
                        "from_alias": "procurement@example.com",
                    },
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["provider_type"] == "imap"
            assert data["from_alias"] == "procurement@example.com"
            assert "credentials_ref" not in data  # never returned
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_add_email_invalid_provider(self):
        """Unknown provider_type → 422."""
        user = make_user()
        ws = make_workspace(user_id=user.id)
        db = make_mock_db(scalar_result=ws)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{ws.id}/shared-email",
                    json={
                        "provider_type": "outlook_legacy",
                        "credentials_ref": "vault://email/1",
                        "from_alias": "test@example.com",
                    },
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_add_email_workspace_not_found(self):
        user = make_user()
        db = make_mock_db(scalar_result=None)

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workspaces/{uuid.uuid4()}/shared-email",
                    json={
                        "provider_type": "gmail",
                        "credentials_ref": "vault://email/1",
                        "from_alias": "test@example.com",
                    },
                )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()


# ── PUT /api/workspaces/{id}/shared-email/{eid} ────────────────────────────────

class TestUpdateSharedEmail:
    @pytest.mark.asyncio
    async def test_update_email_success(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)
        acct = make_email_account(ws.id)

        # Two execute calls: workspace lookup, then email account lookup
        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        acct_result = MagicMock()
        acct_result.scalar_one_or_none.return_value = acct
        db.execute = AsyncMock(side_effect=[ws_result, acct_result])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}/shared-email/{acct.id}",
                    json={
                        "provider_type": "gmail",
                        "credentials_ref": "vault://email/new",
                        "from_alias": "updated@example.com",
                    },
                )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["provider_type"] == "gmail"
            assert data["from_alias"] == "updated@example.com"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_email_not_found(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)

        db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[ws_result, not_found])
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = override_auth(user)
        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put(
                    f"/api/workspaces/{ws.id}/shared-email/{uuid.uuid4()}",
                    json={
                        "provider_type": "imap",
                        "credentials_ref": "vault://email/1",
                        "from_alias": "x@example.com",
                    },
                )
            assert resp.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()
