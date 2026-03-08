"""
Email OAuth2 — Gmail and Microsoft Graph token management.

Handles:
  - Authorization URL generation (with offline access for refresh tokens)
  - Code exchange → access_token + refresh_token
  - Token refresh (when access_token expires)
  - Credential packaging for storage via Fernet encryption

Gmail scopes:
  - https://mail.google.com/ (full IMAP/SMTP access via XOAUTH2)

Microsoft Graph scopes:
  - https://outlook.office365.com/IMAP.AccessAsUser.All
  - https://outlook.office365.com/SMTP.Send
  - offline_access (for refresh tokens)

The encrypted credentials_ref JSON for OAuth accounts:
  {
    "auth_type": "oauth2",
    "provider":  "gmail" | "graph",
    "email":     "user@example.com",
    "access_token": "ya29.xxx",
    "refresh_token": "1//xxx",
    "token_expiry": "2026-03-07T21:00:00+00:00",
    "smtp_host": "smtp.gmail.com",  (provider-specific defaults)
    "smtp_port": 587,
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
  }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import settings
from app.services.secrets import encrypt_api_key, decrypt_api_key

log = structlog.get_logger()

SUPPORTED_EMAIL_PROVIDERS = frozenset({"gmail", "graph"})

_STATE_ALGORITHM = "HS256"
_STATE_TTL_SECONDS = 600  # 10 minutes


# ── Provider configuration ───────────────────────────────────────────────────

_PROVIDER_CONFIG = {
    "gmail": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://mail.google.com/",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
    },
    "graph": {
        "auth_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "scope": "https://outlook.office365.com/IMAP.AccessAsUser.All https://outlook.office365.com/SMTP.Send offline_access",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
    },
}


@dataclass(frozen=True)
class EmailOAuthTokens:
    access_token: str
    refresh_token: str
    email: str
    expires_in: int  # seconds


# ── State management ────────────────────────────────────────────────────────

def create_email_oauth_state(provider: str, workspace_id: str) -> str:
    """Create a signed JWT state token for email OAuth CSRF protection."""
    expire = datetime.now(timezone.utc) + timedelta(seconds=_STATE_TTL_SECONDS)
    return jwt.encode(
        {
            "purpose": "email_oauth_state",
            "provider": provider,
            "workspace_id": workspace_id,
            "exp": expire,
        },
        settings.secret_key,
        algorithm=_STATE_ALGORITHM,
    )


def verify_email_oauth_state(state_token: str, expected_provider: str) -> str:
    """Verify state JWT and return workspace_id. Raises HTTP 400 on failure."""
    try:
        payload = jwt.decode(state_token, settings.secret_key, algorithms=[_STATE_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state — please restart the flow",
        ) from exc

    if payload.get("purpose") != "email_oauth_state":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state purpose")
    if payload.get("provider") != expected_provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider mismatch")

    return payload["workspace_id"]


# ── Client credentials ──────────────────────────────────────────────────────

def _email_client_credentials(provider: str) -> tuple[str, str]:
    """Return (client_id, client_secret) for email OAuth provider."""
    if provider == "gmail":
        client_id = settings.google_client_id
        client_secret = settings.google_client_secret
    elif provider == "graph":
        client_id = settings.microsoft_client_id
        client_secret = settings.microsoft_client_secret
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown email provider: {provider}")

    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Email OAuth provider '{provider}' is not configured",
        )
    return client_id, client_secret


# ── Authorization URL ───────────────────────────────────────────────────────

def build_email_auth_url(provider: str, state: str) -> str:
    """Build OAuth2 authorization URL for email access (with offline/refresh)."""
    if provider not in SUPPORTED_EMAIL_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider: {provider}")

    config = _PROVIDER_CONFIG[provider]
    client_id, _ = _email_client_credentials(provider)
    redirect_uri = f"{settings.sso_redirect_base_url}/api/email-oauth/{provider}/callback"

    auth_url = config["auth_url"]
    if provider == "graph":
        tenant = settings.microsoft_tenant_id or "common"
        auth_url = auth_url.format(tenant=tenant)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
        "access_type": "offline",   # Gmail: request refresh token
        "prompt": "consent",        # Force consent to ensure refresh token
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{auth_url}?{query}"


# ── Token exchange ──────────────────────────────────────────────────────────

async def exchange_email_code(provider: str, code: str, state: str) -> EmailOAuthTokens:
    """Exchange authorization code for access_token + refresh_token."""
    workspace_id = verify_email_oauth_state(state, provider)

    config = _PROVIDER_CONFIG[provider]
    client_id, client_secret = _email_client_credentials(provider)
    redirect_uri = f"{settings.sso_redirect_base_url}/api/email-oauth/{provider}/callback"

    token_url = config["token_url"]
    if provider == "graph":
        tenant = settings.microsoft_tenant_id or "common"
        token_url = token_url.format(tenant=tenant)

    async with httpx.AsyncClient(timeout=15.0) as http:
        token_resp = await http.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Token exchange failed ({provider}): {token_resp.text[:200]}",
            )

        data = token_resp.json()
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"No access_token in {provider} response",
            )

        # Fetch the email address associated with the account
        email_addr = await _fetch_email_address(provider, access_token, http)

    return EmailOAuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        email=email_addr,
        expires_in=int(data.get("expires_in", 3600)),
    )


async def _fetch_email_address(provider: str, access_token: str, http: httpx.AsyncClient) -> str:
    """Fetch the email address from the provider's user profile."""
    if provider == "gmail":
        resp = await http.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json().get("email", "")
    elif provider == "graph":
        resp = await http.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("mail") or data.get("userPrincipalName", "")
    return ""


# ── Token refresh ───────────────────────────────────────────────────────────

async def refresh_oauth_token(provider: str, refresh_token: str) -> dict:
    """Refresh an expired access token. Returns updated token data dict."""
    config = _PROVIDER_CONFIG[provider]
    client_id, client_secret = _email_client_credentials(provider)

    token_url = config["token_url"]
    if provider == "graph":
        tenant = settings.microsoft_tenant_id or "common"
        token_url = token_url.format(tenant=tenant)

    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            log.error("email_oauth.refresh_failed", provider=provider, status=resp.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Token refresh failed ({provider}): {resp.text[:200]}",
            )

        data = resp.json()
        log.info("email_oauth.token_refreshed", provider=provider)
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": int(data.get("expires_in", 3600)),
        }


# ── Credential packaging ───────────────────────────────────────────────────

def package_oauth_credentials(
    provider: str,
    tokens: EmailOAuthTokens,
) -> str:
    """Package OAuth tokens into an encrypted credentials_ref for DB storage."""
    config = _PROVIDER_CONFIG[provider]
    expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in)

    creds = {
        "auth_type": "oauth2",
        "provider": provider,
        "email": tokens.email,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_expiry": expiry.isoformat(),
        "smtp_host": config["smtp_host"],
        "smtp_port": config["smtp_port"],
        "imap_host": config["imap_host"],
        "imap_port": config["imap_port"],
    }
    return encrypt_api_key(json.dumps(creds))


def update_oauth_credentials(
    existing_ref: str,
    refreshed: dict,
) -> str:
    """Update an existing credentials_ref with refreshed tokens."""
    raw = decrypt_api_key(existing_ref)
    creds = json.loads(raw)
    creds["access_token"] = refreshed["access_token"]
    creds["refresh_token"] = refreshed.get("refresh_token", creds["refresh_token"])
    expiry = datetime.now(timezone.utc) + timedelta(seconds=refreshed.get("expires_in", 3600))
    creds["token_expiry"] = expiry.isoformat()
    return encrypt_api_key(json.dumps(creds))
