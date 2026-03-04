from __future__ import annotations
"""
Auth router — email/password registration + login, SSO (Google/GitHub/Microsoft), /me.

All token responses use Bearer JWT (HS256, sub = str(user.id)).
SSO flow:
  GET  /sso/{provider}           → 302 redirect to provider auth page
  GET  /sso/{provider}/callback  → exchange code → JWT
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.workspace import User
from app.services.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.services.sso import (
    SUPPORTED_PROVIDERS,
    build_authorization_url,
    create_sso_state,
    exchange_code_for_user_info,
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    sso_provider: Optional[str] = None


# ── Email / Password Auth ─────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Register a new user with email + password. Returns JWT on success."""
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email (username field) + password. Returns JWT."""
    result = await db.execute(
        select(User).where(User.email == form.username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(str(user.id)))


# ── SSO Auth ─────────────────────────────────────────────────────────────────

@router.get("/sso/{provider}", include_in_schema=True)
async def sso_redirect(provider: str) -> RedirectResponse:
    """
    Start SSO flow: redirect user to the provider's OAuth2 authorization page.
    Supported providers: google, github, microsoft.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported SSO provider '{provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}",
        )
    state = create_sso_state(provider)
    url = build_authorization_url(provider, state)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/sso/{provider}/callback")
async def sso_callback(
    provider: str,
    code: str,
    state: str,
    redirect_uri: Optional[str] = Query(None, description="If set, redirect to this URI with ?token= instead of returning JSON"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth2 callback from provider.
    Verifies state → exchanges code → fetches user info → find-or-create user → JWT.
    If the user's email already exists as a password account, the SSO identity is linked.
    If redirect_uri is provided, redirects to {redirect_uri}?token={jwt} (for browser-based flows).
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported SSO provider: {provider}",
        )

    user_info = await exchange_code_for_user_info(provider, code, state)

    if not user_info.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not retrieve email from {provider}. Ensure email permission is granted.",
        )

    # 1. Find existing user by SSO identity (returning user)
    result = await db.execute(
        select(User).where(User.sso_provider == provider, User.sso_sub == user_info.sub)
    )
    user = result.scalar_one_or_none()

    if not user:
        # 2. Check if email account already exists → link SSO identity to it
        result = await db.execute(select(User).where(User.email == user_info.email))
        user = result.scalar_one_or_none()
        if user:
            user.sso_provider = provider
            user.sso_sub = user_info.sub
        else:
            # 3. Brand new user — create SSO-only account
            user = User(
                email=user_info.email,
                sso_provider=provider,
                sso_sub=user_info.sub,
                password_hash=None,
            )
            db.add(user)

    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))

    if redirect_uri:
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(
            url=f"{redirect_uri}{sep}{urlencode({'token': token})}",
            status_code=status.HTTP_302_FOUND,
        )

    return TokenResponse(access_token=token)


# ── Current User ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's profile. Requires Bearer token."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        is_active=current_user.is_active,
        sso_provider=current_user.sso_provider,
    )
