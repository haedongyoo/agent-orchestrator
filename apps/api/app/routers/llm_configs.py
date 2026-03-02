"""
LLM Config Router

Endpoints for managing per-workspace and per-agent LLM provider configuration
through the UI. Users can set their provider, model, and API key here.

Security rules:
  - API keys are encrypted before storage (Fernet via services/secrets.py).
  - Raw keys are NEVER returned — clients get `has_api_key: bool` instead.
  - Only the workspace owner may read/write configs.
  - Test-connection calls use the stored key; result indicates success/failure only.
"""
from __future__ import annotations

import uuid
from typing import Optional

import litellm
import litellm.exceptions
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.llm_config import LLMConfig
from app.services.llm_registry import PROVIDERS, VALID_MODEL_IDS, get_provider_for_model
from app.services.secrets import encrypt_api_key, decrypt_api_key

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class LLMConfigSet(BaseModel):
    """Payload for creating or updating an LLM config."""
    model: str
    api_key: Optional[str] = None       # raw key from UI — encrypted before storage
    api_base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 1.0

    @field_validator("model")
    @classmethod
    def model_must_be_known(cls, v: str) -> str:
        if v not in VALID_MODEL_IDS:
            raise ValueError(
                f"Unknown model '{v}'. "
                f"Use GET /api/llm/providers to see supported models."
            )
        return v

    @field_validator("temperature")
    @classmethod
    def temperature_range(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v


class LLMConfigResponse(BaseModel):
    """Safe representation — never includes the raw API key."""
    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    model: str
    has_api_key: bool           # True if an encrypted key is stored
    api_base_url: Optional[str]
    max_tokens: int
    temperature: float
    is_active: bool

    class Config:
        from_attributes = True


class TestConnectionResponse(BaseModel):
    success: bool
    model: str
    message: str
    response_preview: Optional[str] = None   # first 100 chars of model reply


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_response(cfg: LLMConfig) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=cfg.id,
        workspace_id=cfg.workspace_id,
        agent_id=cfg.agent_id,
        model=cfg.model,
        has_api_key=cfg.api_key_encrypted is not None,
        api_base_url=cfg.api_base_url,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        is_active=cfg.is_active,
    )


async def _get_config(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
) -> LLMConfig | None:
    result = await db.execute(
        select(LLMConfig).where(
            LLMConfig.workspace_id == workspace_id,
            LLMConfig.agent_id == agent_id,
        )
    )
    return result.scalar_one_or_none()


# ── Workspace-level config ─────────────────────────────────────────────────────

@router.get(
    "/workspaces/{workspace_id}/llm-config",
    response_model=LLMConfigResponse,
    summary="Get workspace-level LLM config (default for all agents)",
)
async def get_workspace_llm_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=None)
    if not cfg:
        raise HTTPException(status_code=404, detail="No LLM config set for this workspace")
    return _to_response(cfg)


@router.post(
    "/workspaces/{workspace_id}/llm-config",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Set or update workspace-level LLM config",
)
async def set_workspace_llm_config(
    workspace_id: uuid.UUID,
    body: LLMConfigSet,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=None)
    if not cfg:
        cfg = LLMConfig(workspace_id=workspace_id, agent_id=None, model=body.model)
        db.add(cfg)

    cfg.model        = body.model
    cfg.api_base_url = body.api_base_url
    cfg.max_tokens   = body.max_tokens
    cfg.temperature  = body.temperature

    if body.api_key is not None:
        provider = get_provider_for_model(body.model)
        if provider and provider["requires_api_key"] and not body.api_key.strip():
            raise HTTPException(status_code=400, detail="This provider requires an API key")
        cfg.api_key_encrypted = encrypt_api_key(body.api_key) if body.api_key.strip() else None

    await db.flush()
    return _to_response(cfg)


@router.delete(
    "/workspaces/{workspace_id}/llm-config",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove workspace-level LLM config",
)
async def delete_workspace_llm_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=None)
    if cfg:
        await db.delete(cfg)


@router.post(
    "/workspaces/{workspace_id}/llm-config/test",
    response_model=TestConnectionResponse,
    summary="Test the workspace-level LLM config with a live API call",
)
async def test_workspace_llm_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=None)
    if not cfg:
        raise HTTPException(status_code=404, detail="No LLM config set for this workspace")
    return await _test_config(cfg)


# ── Agent-level config (override) ─────────────────────────────────────────────

@router.get(
    "/workspaces/{workspace_id}/agents/{agent_id}/llm-config",
    response_model=LLMConfigResponse,
    summary="Get the effective LLM config for an agent (override or workspace default)",
)
async def get_agent_llm_config(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    # Agent override first, then workspace default
    cfg = await _get_config(db, workspace_id, agent_id=agent_id)
    if not cfg:
        cfg = await _get_config(db, workspace_id, agent_id=None)
    if not cfg:
        raise HTTPException(status_code=404, detail="No LLM config set (agent or workspace)")
    return _to_response(cfg)


@router.post(
    "/workspaces/{workspace_id}/agents/{agent_id}/llm-config",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Set or update a per-agent LLM config override",
)
async def set_agent_llm_config(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: LLMConfigSet,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=agent_id)
    if not cfg:
        cfg = LLMConfig(workspace_id=workspace_id, agent_id=agent_id, model=body.model)
        db.add(cfg)

    cfg.model        = body.model
    cfg.api_base_url = body.api_base_url
    cfg.max_tokens   = body.max_tokens
    cfg.temperature  = body.temperature

    if body.api_key is not None:
        cfg.api_key_encrypted = encrypt_api_key(body.api_key) if body.api_key.strip() else None

    await db.flush()
    return _to_response(cfg)


@router.delete(
    "/workspaces/{workspace_id}/agents/{agent_id}/llm-config",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove per-agent override — agent falls back to workspace default",
)
async def delete_agent_llm_config(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=agent_id)
    if cfg:
        await db.delete(cfg)


@router.post(
    "/workspaces/{workspace_id}/agents/{agent_id}/llm-config/test",
    response_model=TestConnectionResponse,
    summary="Test the effective LLM config for an agent",
)
async def test_agent_llm_config(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db, workspace_id, agent_id=agent_id) \
       or await _get_config(db, workspace_id, agent_id=None)
    if not cfg:
        raise HTTPException(status_code=404, detail="No LLM config set (agent or workspace)")
    return await _test_config(cfg)


# ── Provider / model discovery (for UI dropdowns) ──────────────────────────────

@router.get(
    "/llm/providers",
    summary="List all supported LLM providers",
)
async def list_providers():
    """Returns provider metadata including whether API key / base URL is required."""
    return [
        {
            "id":                  p["id"],
            "name":                p["name"],
            "requires_api_key":    p["requires_api_key"],
            "requires_base_url":   p["requires_base_url"],
            "base_url_placeholder":p["base_url_placeholder"],
            "api_key_label":       p["api_key_label"],
            "docs_url":            p["docs_url"],
            "note":                p["note"],
        }
        for p in PROVIDERS
    ]


@router.get(
    "/llm/providers/{provider_id}/models",
    summary="List models available for a given provider",
)
async def list_provider_models(provider_id: str):
    from app.services.llm_registry import get_provider
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'")
    return provider["models"]


# ── Internal helper ────────────────────────────────────────────────────────────

async def _test_config(cfg: LLMConfig) -> TestConnectionResponse:
    """Make a minimal live API call to verify the stored config works."""
    api_key  = decrypt_api_key(cfg.api_key_encrypted) if cfg.api_key_encrypted else None
    api_base = cfg.api_base_url or None

    try:
        response = await litellm.acompletion(
            model=cfg.model,
            messages=[{"role": "user", "content": 'Reply with exactly the word "ok".'}],
            max_tokens=10,
            temperature=0,
            **({"api_key":  api_key}  if api_key  else {}),
            **({"api_base": api_base} if api_base else {}),
        )
        reply = response.choices[0].message.content or ""
        return TestConnectionResponse(
            success=True,
            model=cfg.model,
            message="Connection successful",
            response_preview=reply[:100],
        )
    except litellm.exceptions.AuthenticationError:
        return TestConnectionResponse(
            success=False, model=cfg.model,
            message="Authentication failed — check your API key",
        )
    except litellm.exceptions.NotFoundError:
        return TestConnectionResponse(
            success=False, model=cfg.model,
            message="Model not found — check the model name and base URL",
        )
    except Exception as exc:
        return TestConnectionResponse(
            success=False, model=cfg.model,
            message=f"Connection failed: {type(exc).__name__}: {exc}",
        )
