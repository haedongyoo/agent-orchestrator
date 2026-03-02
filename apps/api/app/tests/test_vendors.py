"""
Tests for the Vendor/Contractor CRM.

GET /api/workspaces/{id}/vendors
POST /api/workspaces/{id}/vendors           (upsert semantics)
GET /api/workspaces/{id}/vendors/{vid}
PUT /api/workspaces/{id}/vendors/{vid}
DELETE /api/workspaces/{id}/vendors/{vid}
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Mock celery before any module that depends on it is imported
_celery_mock = MagicMock()
sys.modules.setdefault("celery", _celery_mock)
sys.modules.setdefault("app.worker", MagicMock(celery_app=MagicMock()))

from app.services.vendors import upsert_vendor, list_vendors, get_vendor, delete_vendor  # noqa: E402
from app.tasks.vendor_ops import _do_upsert  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────

def _vendor_mock(workspace_id=None, name="ACME Supplies", **kwargs):
    """Build a MagicMock that mimics a Vendor ORM row."""
    v = MagicMock()
    v.id = kwargs.get("id", uuid.uuid4())
    v.workspace_id = workspace_id or uuid.uuid4()
    v.name = name
    v.email = kwargs.get("email")
    v.category = kwargs.get("category")
    v.contact_name = kwargs.get("contact_name")
    v.phone = kwargs.get("phone")
    v.website = kwargs.get("website")
    v.country = kwargs.get("country")
    v.notes = kwargs.get("notes")
    v.tags = kwargs.get("tags", [])
    now = datetime.now(timezone.utc)
    v.created_at = now
    v.updated_at = now
    return v


# ── Service layer tests ────────────────────────────────────────────────────────

class TestUpsertVendorService:
    @pytest.mark.asyncio
    async def test_creates_new_vendor(self):
        db = AsyncMock(spec=AsyncSession)
        ws_id = uuid.uuid4()

        no_result = MagicMock()
        no_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=no_result)
        db.add = MagicMock()
        db.flush = AsyncMock()

        vendor = await upsert_vendor(db, workspace_id=ws_id, name="ACME", email="acme@example.com")

        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        assert vendor.name == "ACME"
        assert vendor.email == "acme@example.com"
        assert vendor.workspace_id == ws_id

    @pytest.mark.asyncio
    async def test_updates_existing_vendor(self):
        db = AsyncMock(spec=AsyncSession)
        ws_id = uuid.uuid4()
        existing = _vendor_mock(workspace_id=ws_id, name="ACME", email="old@example.com")

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=existing_result)
        db.add = MagicMock()
        db.flush = AsyncMock()

        vendor = await upsert_vendor(db, workspace_id=ws_id, name="ACME", email="new@example.com", notes="Updated")

        db.add.assert_not_called()  # no new row
        assert vendor.email == "new@example.com"
        assert vendor.notes == "Updated"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_none_fields(self):
        db = AsyncMock(spec=AsyncSession)
        ws_id = uuid.uuid4()
        existing = _vendor_mock(workspace_id=ws_id, name="ACME", email="keep@example.com")

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=existing_result)
        db.flush = AsyncMock()

        # email=None means "don't overwrite"
        vendor = await upsert_vendor(db, workspace_id=ws_id, name="ACME", notes="New note")

        assert vendor.email == "keep@example.com"  # unchanged
        assert vendor.notes == "New note"

    @pytest.mark.asyncio
    async def test_list_vendors_returns_all(self):
        db = AsyncMock(spec=AsyncSession)
        ws_id = uuid.uuid4()
        rows = [_vendor_mock(workspace_id=ws_id, name=f"Vendor {i}") for i in range(3)]

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)

        vendors = await list_vendors(db, ws_id)
        assert len(vendors) == 3

    @pytest.mark.asyncio
    async def test_get_vendor_returns_none_on_miss(self):
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        vendor = await get_vendor(db, uuid.uuid4(), uuid.uuid4())
        assert vendor is None

    @pytest.mark.asyncio
    async def test_delete_vendor_returns_false_on_miss(self):
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        deleted = await delete_vendor(db, uuid.uuid4(), uuid.uuid4())
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_vendor_removes_row(self):
        db = AsyncMock(spec=AsyncSession)
        ws_id = uuid.uuid4()
        existing = _vendor_mock(workspace_id=ws_id, name="ToDelete")

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock()

        deleted = await delete_vendor(db, ws_id, existing.id)
        assert deleted is True
        db.delete.assert_awaited_once_with(existing)


# ── HTTP endpoint tests ────────────────────────────────────────────────────────

def _make_test_app(user):
    from app.db.session import get_db
    from app.services.auth import get_current_user
    from app.routers.vendors import router as vendors_router

    app = FastAPI()
    app.include_router(vendors_router, prefix="/api/workspaces")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    return app


class TestVendorEndpoints:
    def _user(self):
        u = MagicMock()
        u.id = uuid.uuid4()
        return u

    def _workspace(self, user):
        ws = MagicMock()
        ws.id = uuid.uuid4()
        ws.user_id = user.id
        return ws

    @pytest.mark.asyncio
    async def test_list_vendors_empty(self):
        user = self._user()
        ws = self._workspace(user)

        with (
            patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)),
            patch("app.routers.vendors.list_vendors", new=AsyncMock(return_value=[])),
        ):
            app = _make_test_app(user)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/workspaces/{ws.id}/vendors")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_upsert_creates_vendor(self):
        user = self._user()
        ws = self._workspace(user)
        vendor = _vendor_mock(workspace_id=ws.id, name="ACME", email="acme@example.com")

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        db_mock.refresh = AsyncMock()

        with (
            patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)),
            patch("app.routers.vendors.upsert_vendor", new=AsyncMock(return_value=vendor)),
        ):
            from app.db.session import get_db
            from app.services.auth import get_current_user
            from app.routers.vendors import router as vendors_router

            app = FastAPI()
            app.include_router(vendors_router, prefix="/api/workspaces")
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_db] = lambda: db_mock

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/workspaces/{ws.id}/vendors",
                    json={"name": "ACME", "email": "acme@example.com"},
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["name"] == "ACME"

    @pytest.mark.asyncio
    async def test_get_vendor_404_on_miss(self):
        user = self._user()
        ws = self._workspace(user)

        with (
            patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)),
            patch("app.routers.vendors.get_vendor", new=AsyncMock(return_value=None)),
        ):
            app = _make_test_app(user)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/api/workspaces/{ws.id}/vendors/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_vendor_no_content(self):
        user = self._user()
        ws = self._workspace(user)

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()

        with (
            patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)),
            patch("app.routers.vendors.delete_vendor", new=AsyncMock(return_value=True)),
        ):
            from app.db.session import get_db
            from app.services.auth import get_current_user
            from app.routers.vendors import router as vendors_router

            app = FastAPI()
            app.include_router(vendors_router, prefix="/api/workspaces")
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_db] = lambda: db_mock

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.delete(f"/api/workspaces/{ws.id}/vendors/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_204_NO_CONTENT

    @pytest.mark.asyncio
    async def test_delete_vendor_404_on_miss(self):
        user = self._user()
        ws = self._workspace(user)

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()

        with (
            patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)),
            patch("app.routers.vendors.delete_vendor", new=AsyncMock(return_value=False)),
        ):
            from app.db.session import get_db
            from app.services.auth import get_current_user
            from app.routers.vendors import router as vendors_router

            app = FastAPI()
            app.include_router(vendors_router, prefix="/api/workspaces")
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_db] = lambda: db_mock

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.delete(f"/api/workspaces/{ws.id}/vendors/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_invalid_category_returns_422(self):
        user = self._user()
        ws = self._workspace(user)

        with patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)):
            app = _make_test_app(user)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/workspaces/{ws.id}/vendors",
                    json={"name": "ACME", "category": "INVALID_CATEGORY"},
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_list_vendors_category_filter(self):
        user = self._user()
        ws = self._workspace(user)
        rows = [_vendor_mock(workspace_id=ws.id, name="Oak Factory", category="furniture_supplier")]

        with (
            patch("app.routers.vendors._get_workspace_or_404", new=AsyncMock(return_value=ws)),
            patch("app.routers.vendors.list_vendors", new=AsyncMock(return_value=rows)) as mock_list,
        ):
            app = _make_test_app(user)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(
                    f"/api/workspaces/{ws.id}/vendors",
                    params={"category": "furniture_supplier"},
                )
            assert resp.status_code == status.HTTP_200_OK
            # Verify category was passed to the service
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs.get("category") == "furniture_supplier"


# ── Vendor ops task tests ──────────────────────────────────────────────────────

class TestDoUpsert:
    """Tests for the async _do_upsert helper (no Celery dependency)."""

    @pytest.mark.asyncio
    async def test_missing_name_returns_error(self):
        result = await _do_upsert({"workspace_id": str(uuid.uuid4())})
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_workspace_id_returns_error(self):
        result = await _do_upsert({"name": "ACME"})
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_workspace_id_returns_error(self):
        result = await _do_upsert({"workspace_id": "not-a-uuid", "name": "ACME"})
        assert result["success"] is False
        assert "Invalid workspace_id" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_request_calls_upsert(self):
        ws_id = str(uuid.uuid4())
        vendor = _vendor_mock(name="ACME")

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.db.session.AsyncSessionLocal", return_value=mock_db),
            patch("app.services.vendors.upsert_vendor", new=AsyncMock(return_value=vendor)),
        ):
            result = await _do_upsert({"workspace_id": ws_id, "name": "ACME", "email": "a@b.com"})

        assert result["success"] is True
        assert result["name"] == "ACME"
