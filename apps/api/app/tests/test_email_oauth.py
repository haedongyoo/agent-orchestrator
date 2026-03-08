"""
Tests for Email OAuth2 — Gmail and Microsoft Graph integration.

Coverage:
  - email_oauth service: state creation/verification, credential packaging
  - email connector: _is_oauth, _build_xoauth2_string
  - router: authorize redirect (success, bad provider, wrong owner), callback
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.workspace import User, Workspace, SharedEmailAccount
from app.routers.email_oauth import router as email_oauth_router
from app.services.auth import create_access_token, get_current_user
from app.services.email_oauth import (
    create_email_oauth_state,
    verify_email_oauth_state,
    package_oauth_credentials,
    update_oauth_credentials,
    EmailOAuthTokens,
)
from app.services.connectors.email import _is_oauth, _build_xoauth2_string

app = FastAPI()
app.include_router(email_oauth_router, prefix="/api/email-oauth")


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


# ── State management tests ──────────────────────────────────────────────────

class TestEmailOAuthState:
    def test_create_and_verify_state(self):
        ws_id = str(uuid.uuid4())
        state = create_email_oauth_state("gmail", ws_id)
        result = verify_email_oauth_state(state, "gmail")
        assert result == ws_id

    def test_verify_state_wrong_provider_raises(self):
        state = create_email_oauth_state("gmail", str(uuid.uuid4()))
        with pytest.raises(Exception):  # HTTPException
            verify_email_oauth_state(state, "graph")

    def test_verify_state_invalid_token_raises(self):
        with pytest.raises(Exception):
            verify_email_oauth_state("invalid.token.here", "gmail")


# ── Credential packaging tests ──────────────────────────────────────────────

class TestCredentialPackaging:
    def test_package_and_decrypt_gmail(self):
        tokens = EmailOAuthTokens(
            access_token="ya29.test",
            refresh_token="1//test",
            email="user@gmail.com",
            expires_in=3600,
        )
        encrypted = package_oauth_credentials("gmail", tokens)
        assert isinstance(encrypted, str)
        assert len(encrypted) > 50  # encrypted blob is long

        # Decrypt and verify
        from app.services.secrets import decrypt_api_key
        raw = json.loads(decrypt_api_key(encrypted))
        assert raw["auth_type"] == "oauth2"
        assert raw["provider"] == "gmail"
        assert raw["email"] == "user@gmail.com"
        assert raw["access_token"] == "ya29.test"
        assert raw["refresh_token"] == "1//test"
        assert raw["smtp_host"] == "smtp.gmail.com"
        assert raw["imap_host"] == "imap.gmail.com"

    def test_package_graph(self):
        tokens = EmailOAuthTokens(
            access_token="eyJ0.test",
            refresh_token="M.test",
            email="user@outlook.com",
            expires_in=3600,
        )
        encrypted = package_oauth_credentials("graph", tokens)
        from app.services.secrets import decrypt_api_key
        raw = json.loads(decrypt_api_key(encrypted))
        assert raw["provider"] == "graph"
        assert raw["smtp_host"] == "smtp.office365.com"
        assert raw["imap_host"] == "outlook.office365.com"

    def test_update_oauth_credentials(self):
        tokens = EmailOAuthTokens(
            access_token="old_token",
            refresh_token="old_refresh",
            email="user@gmail.com",
            expires_in=3600,
        )
        encrypted = package_oauth_credentials("gmail", tokens)

        refreshed = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 7200,
        }
        updated_ref = update_oauth_credentials(encrypted, refreshed)

        from app.services.secrets import decrypt_api_key
        raw = json.loads(decrypt_api_key(updated_ref))
        assert raw["access_token"] == "new_token"
        assert raw["refresh_token"] == "new_refresh"
        assert raw["email"] == "user@gmail.com"  # preserved


# ── Email connector helpers ─────────────────────────────────────────────────

class TestEmailConnectorHelpers:
    def test_is_oauth_true(self):
        assert _is_oauth({"auth_type": "oauth2"}) is True

    def test_is_oauth_false_password(self):
        assert _is_oauth({"username": "user", "password": "pass"}) is False

    def test_is_oauth_false_empty(self):
        assert _is_oauth({}) is False

    def test_build_xoauth2_string(self):
        result = _build_xoauth2_string("user@gmail.com", "token123")
        assert isinstance(result, str)
        # Decode and verify format
        import base64
        decoded = base64.b64decode(result).decode()
        assert "user=user@gmail.com" in decoded
        assert "auth=Bearer token123" in decoded


# ── Router tests ─────────────────────────────────────────────────────────────

class TestEmailOAuthAuthorize:
    @pytest.mark.asyncio
    async def test_authorize_redirect_gmail(self):
        user = make_user()
        ws = make_workspace(user_id=user.id)

        mock_db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = ws
        mock_db.execute = AsyncMock(return_value=ws_result)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            with patch("app.services.email_oauth.settings") as mock_settings:
                mock_settings.google_client_id = "test-client-id"
                mock_settings.google_client_secret = "test-secret"
                mock_settings.sso_redirect_base_url = "http://localhost:8000"
                mock_settings.secret_key = "test-key"

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    follow_redirects=False,
                ) as client:
                    token = create_access_token(str(user.id))
                    resp = await client.get(
                        f"/api/email-oauth/gmail/authorize?workspace_id={ws.id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )

                assert resp.status_code == 302
                location = resp.headers["location"]
                assert "accounts.google.com" in location
                assert "test-client-id" in location
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_authorize_bad_provider(self):
        user = make_user()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/email-oauth/yahoo/authorize?workspace_id={uuid.uuid4()}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_authorize_wrong_owner_404(self):
        user = make_user()

        mock_db = AsyncMock()
        ws_result = MagicMock()
        ws_result.scalar_one_or_none.return_value = None  # not owned
        mock_db.execute = AsyncMock(return_value=ws_result)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = create_access_token(str(user.id))
                resp = await client.get(
                    f"/api/email-oauth/gmail/authorize?workspace_id={uuid.uuid4()}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestEmailOAuthCallback:
    @pytest.mark.asyncio
    async def test_callback_creates_account(self):
        ws_id = uuid.uuid4()
        state = create_email_oauth_state("gmail", str(ws_id))

        tokens = EmailOAuthTokens(
            access_token="ya29.test",
            refresh_token="1//test",
            email="user@gmail.com",
            expires_in=3600,
        )

        mock_db = AsyncMock()
        # First execute: check existing SharedEmailAccount
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=existing_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        # Mock refresh to return the account
        account = SharedEmailAccount(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            provider_type="gmail",
            credentials_ref="encrypted",
            from_alias="user@gmail.com",
            is_active=True,
        )
        mock_db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', account.id) or setattr(obj, 'workspace_id', ws_id))

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("app.routers.email_oauth.exchange_email_code", AsyncMock(return_value=tokens)), \
                 patch("app.routers.email_oauth.verify_email_oauth_state", return_value=str(ws_id)), \
                 patch("app.routers.email_oauth.package_oauth_credentials", return_value="encrypted_ref"):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.get(
                        f"/api/email-oauth/gmail/callback?code=test_code&state={state}",
                    )

                assert resp.status_code == 200
                data = resp.json()
                assert data["provider_type"] == "gmail"
                assert data["from_alias"] == "user@gmail.com"
                assert data["is_active"] is True
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_callback_bad_provider(self):
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/email-oauth/yahoo/callback?code=test&state=test",
                )

            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()
