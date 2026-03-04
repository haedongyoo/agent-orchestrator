from __future__ import annotations
"""
Auth endpoint tests.

Tests use FastAPI dependency overrides to mock the DB session.
No real DB connection is required — all DB calls are intercepted via AsyncMock.

Coverage:
  - POST /api/auth/register   (success, duplicate email)
  - POST /api/auth/login      (success, wrong password, unknown user)
  - GET  /api/auth/me         (authenticated, unauthenticated)
  - GET  /api/auth/sso/{p}    (redirect, unsupported provider)
  - GET  /api/auth/sso/{p}/callback (mocked exchange, new user, link existing)
"""
import uuid
from datetime import timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient, ASGITransport

# Use a minimal FastAPI app to avoid importing ContainerManager / docker SDK
from app.routers.auth import router as auth_router
from app.db.session import get_db
from app.models.workspace import User
from app.services.auth import create_access_token, hash_password

# Minimal test app — only the auth router mounted
app = FastAPI()
app.include_router(auth_router, prefix="/api/auth")


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_user(
    email: str = "test@example.com",
    password: str = "password123",
    sso_provider: Optional[str] = None,
    sso_sub: Optional[str] = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password) if not sso_provider else None,
        sso_provider=sso_provider,
        sso_sub=sso_sub,
        is_active=True,
    )
    return user


def make_mock_db(scalar_result=None):
    """Return a mock AsyncSession whose execute() returns the given scalar."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def override_db(request):
    """Fixture: swap get_db with a mock that returns request.param as the DB."""
    mock_db = request.param if hasattr(request, "param") else make_mock_db()

    async def _get_db_override():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db_override
    yield mock_db
    app.dependency_overrides.clear()


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self):
        """New email → 201 + access_token."""
        db = make_mock_db(scalar_result=None)  # no existing user

        # After db.refresh, user needs an id — simulate by setting it on the User arg
        async def _refresh(obj):
            obj.id = uuid.uuid4()

        db.refresh.side_effect = _refresh

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/register",
                    json={"email": "new@example.com", "password": "securepass"},
                )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self):
        """Existing email → 409 Conflict."""
        existing_user = make_user(email="taken@example.com")
        db = make_mock_db(scalar_result=existing_user)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/register",
                    json={"email": "taken@example.com", "password": "securepass"},
                )
            assert resp.status_code == status.HTTP_409_CONFLICT
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_register_short_password(self):
        """Password < 8 chars → 422 Validation Error."""
        db = make_mock_db(scalar_result=None)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/register",
                    json={"email": "new@example.com", "password": "short"},
                )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Correct credentials → 200 + access_token."""
        user = make_user(email="user@example.com", password="mypassword")
        db = make_mock_db(scalar_result=user)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/login",
                    data={"username": "user@example.com", "password": "mypassword"},
                )
            assert resp.status_code == status.HTTP_200_OK
            assert "access_token" in resp.json()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        """Wrong password → 401."""
        user = make_user(email="user@example.com", password="correctpass")
        db = make_mock_db(scalar_result=user)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/login",
                    data={"username": "user@example.com", "password": "wrongpass"},
                )
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login_unknown_email(self):
        """Unknown email → 401."""
        db = make_mock_db(scalar_result=None)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/login",
                    data={"username": "nobody@example.com", "password": "pass"},
                )
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        finally:
            app.dependency_overrides.clear()


# ── /me endpoint ──────────────────────────────────────────────────────────────

class TestGetMe:
    @pytest.mark.asyncio
    async def test_me_authenticated(self):
        """Valid JWT → 200 + user data."""
        user = make_user(email="me@example.com")
        db = make_mock_db(scalar_result=user)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        token = create_access_token(str(user.id))
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["email"] == "me@example.com"
            assert data["is_active"] is True
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self):
        """No token → 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/auth/me")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_me_expired_token(self):
        """Expired token → 401."""
        user = make_user()
        token = create_access_token(str(user.id), expires_delta=timedelta(seconds=-1))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── SSO redirect ──────────────────────────────────────────────────────────────

class TestSSORedirect:
    @pytest.mark.asyncio
    async def test_sso_redirect_google(self):
        """GET /sso/google → 302 redirect to accounts.google.com."""
        with patch("app.services.sso.settings") as mock_settings:
            mock_settings.google_client_id = "test-client-id"
            mock_settings.google_client_secret = "test-secret"
            mock_settings.sso_redirect_base_url = "http://localhost:8000"
            mock_settings.secret_key = "test-secret-key"
            mock_settings.microsoft_tenant_id = "common"

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
            ) as client:
                resp = await client.get("/api/auth/sso/google")

        assert resp.status_code == status.HTTP_302_FOUND
        assert "accounts.google.com" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_sso_redirect_unsupported_provider(self):
        """Unknown provider → 400."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/auth/sso/linkedin")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ── SSO callback ──────────────────────────────────────────────────────────────

class TestSSOCallback:
    @pytest.mark.asyncio
    async def test_sso_callback_creates_new_user(self):
        """Valid callback with unknown SSO sub → create new user → JWT."""
        from app.services.sso import SSOUserInfo

        new_user_id = uuid.uuid4()
        db = AsyncMock()

        # First execute: lookup by sso (not found); second: lookup by email (not found)
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=not_found)

        async def _refresh(obj):
            obj.id = new_user_id

        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=_refresh)

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override

        mock_user_info = SSOUserInfo(
            provider="google",
            sub="google-uid-12345",
            email="newgoogle@example.com",
            name="Google User",
        )

        try:
            # Patch exchange_code_for_user_info at the router import level — this also
            # skips verify_sso_state since the whole function is replaced.
            with patch(
                "app.routers.auth.exchange_code_for_user_info",
                AsyncMock(return_value=mock_user_info),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get(
                        "/api/auth/sso/google/callback",
                        params={"code": "auth-code-123", "state": "fake-state"},
                    )
            assert resp.status_code == status.HTTP_200_OK
            assert "access_token" in resp.json()
        finally:
            app.dependency_overrides.clear()
