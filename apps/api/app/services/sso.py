from __future__ import annotations
"""
SSO OAuth2 integration — Google, GitHub, Microsoft.

Flow:
  1. GET /api/auth/sso/{provider}
       → generate signed state token (JWT, 10-min TTL)
       → redirect user to provider's authorization URL

  2. GET /api/auth/sso/{provider}/callback?code=...&state=...
       → verify state JWT (provider + expiry)
       → exchange code for access_token at provider token endpoint
       → fetch user profile (email, stable sub ID)
       → return SSOUserInfo to caller

State is encoded as a short-lived JWT (HS256) to avoid Redis coupling.
The callback endpoint verifies the state before trusting the code.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import settings

SSOProviderName = Literal["google", "github", "microsoft"]
SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"google", "github", "microsoft"})

_STATE_ALGORITHM = "HS256"
_STATE_TTL_SECONDS = 600  # 10 minutes


@dataclass(frozen=True)
class SSOUserInfo:
    provider: str
    sub: str          # stable, provider-unique user ID (never changes)
    email: str        # may be empty if provider blocks access — caller must validate
    name: Optional[str] = None


# ── State helpers ─────────────────────────────────────────────────────────────

def create_sso_state(provider: str) -> str:
    """Return a signed JWT encoding provider + expiry for CSRF protection."""
    expire = datetime.now(timezone.utc) + timedelta(seconds=_STATE_TTL_SECONDS)
    return jwt.encode(
        {"purpose": "sso_state", "provider": provider, "exp": expire},
        settings.secret_key,
        algorithm=_STATE_ALGORITHM,
    )


def verify_sso_state(state_token: str, expected_provider: str) -> None:
    """Raise HTTP 400 if state is invalid, expired, or provider mismatches."""
    try:
        payload = jwt.decode(state_token, settings.secret_key, algorithms=[_STATE_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO state — please restart the login flow",
        ) from exc

    if payload.get("purpose") != "sso_state":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid SSO state purpose")
    if payload.get("provider") != expected_provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO provider mismatch")


# ── Provider config ───────────────────────────────────────────────────────────

def _provider_urls(provider: str) -> dict[str, str]:
    tenant = settings.microsoft_tenant_id or "common"
    urls: dict[str, dict[str, str]] = {
        "google": {
            "auth": "https://accounts.google.com/o/oauth2/v2/auth",
            "token": "https://oauth2.googleapis.com/token",
            "userinfo": "https://www.googleapis.com/oauth2/v2/userinfo",
            "scope": "openid email profile",
        },
        "github": {
            "auth": "https://github.com/login/oauth/authorize",
            "token": "https://github.com/login/oauth/access_token",
            "userinfo": "https://api.github.com/user",
            "scope": "read:user user:email",
        },
        "microsoft": {
            "auth": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            "token": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            "userinfo": "https://graph.microsoft.com/v1.0/me",
            "scope": "openid email profile",
        },
    }
    if provider not in urls:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown SSO provider: {provider}")
    return urls[provider]


def _client_credentials(provider: str) -> tuple[str, str]:
    """Return (client_id, client_secret); raises 503 if provider is not configured."""
    mapping = {
        "google": (settings.google_client_id, settings.google_client_secret),
        "github": (settings.github_client_id, settings.github_client_secret),
        "microsoft": (settings.microsoft_client_id, settings.microsoft_client_secret),
    }
    if provider not in mapping:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown SSO provider: {provider}")
    client_id, client_secret = mapping[provider]
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SSO provider '{provider}' is not configured on this server",
        )
    return client_id, client_secret


# ── Authorization URL ─────────────────────────────────────────────────────────

def build_authorization_url(provider: str, state: str) -> str:
    """Build the provider OAuth2 authorization URL with state and redirect_uri."""
    urls = _provider_urls(provider)
    client_id, _ = _client_credentials(provider)
    redirect_uri = f"{settings.sso_redirect_base_url}/api/auth/sso/{provider}/callback"

    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": urls["scope"],
        "state": state,
    }
    if provider in ("google", "microsoft"):
        params["access_type"] = "online"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{urls['auth']}?{query}"


# ── Code exchange + user info ─────────────────────────────────────────────────

async def exchange_code_for_user_info(provider: str, code: str, state: str) -> SSOUserInfo:
    """
    Full OAuth2 code exchange:
      1. Verify state JWT.
      2. POST code to provider token endpoint → access_token.
      3. GET user profile from provider userinfo endpoint.
      4. For GitHub: follow-up call if email is private.
    """
    verify_sso_state(state, provider)

    urls = _provider_urls(provider)
    client_id, client_secret = _client_credentials(provider)
    redirect_uri = f"{settings.sso_redirect_base_url}/api/auth/sso/{provider}/callback"

    async with httpx.AsyncClient(timeout=15.0) as http:
        # Step 1: exchange authorization code for access token
        token_resp = await http.post(
            urls["token"],
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

        access_token: str = token_resp.json().get("access_token", "")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"No access_token in {provider} response",
            )

        # Step 2: fetch user profile
        profile_resp = await http.get(
            urls["userinfo"],
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if profile_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"User info fetch failed ({provider}): {profile_resp.text[:200]}",
            )
        profile = profile_resp.json()

        # Step 3 (GitHub only): fetch primary verified email if profile email is private
        email = _extract_email(provider, profile)
        if provider == "github" and not email:
            email_resp = await http.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if email_resp.status_code == 200:
                emails = email_resp.json()
                email = next(
                    (e["email"] for e in emails if e.get("primary") and e.get("verified")),
                    "",
                )

    return SSOUserInfo(
        provider=provider,
        sub=_extract_sub(provider, profile),
        email=email,
        name=_extract_name(provider, profile),
    )


# ── Profile field extractors ──────────────────────────────────────────────────

def _extract_sub(provider: str, data: dict) -> str:
    if provider in ("google", "github"):
        return str(data["id"])
    if provider == "microsoft":
        return data["id"]
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider: {provider}")


def _extract_email(provider: str, data: dict) -> str:
    if provider == "google":
        return data.get("email", "")
    if provider == "github":
        return data.get("email") or ""
    if provider == "microsoft":
        return data.get("mail") or data.get("userPrincipalName", "")
    return ""


def _extract_name(provider: str, data: dict) -> Optional[str]:
    return data.get("name") or data.get("displayName")
