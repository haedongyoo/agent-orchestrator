"""
Role Templates router

Endpoints:
  GET  /api/agent-templates             → list all built-in templates
  GET  /api/agent-templates/{id}        → get single template by id

No auth required — templates are public metadata (no sensitive data).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.role_templates import get_template, list_templates

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class RoleTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    role_prompt: str
    allowed_tools: List[str]
    rate_limit_per_min: int
    max_concurrency: int

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/agent-templates",
    response_model=List[RoleTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="List all built-in agent role templates",
)
async def list_agent_templates() -> List[RoleTemplateResponse]:
    """
    Return all built-in role templates.

    Use these to pre-fill agent creation:
      1. GET /api/agent-templates to browse available roles.
      2. POST /api/workspaces/{id}/agents with the template's fields
         (optionally override any field).
    """
    templates = list_templates()
    return [RoleTemplateResponse(**vars(t)) for t in templates]


@router.get(
    "/agent-templates/{template_id}",
    response_model=RoleTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single role template by id",
)
async def get_agent_template(template_id: str) -> RoleTemplateResponse:
    """
    Return a single built-in role template.

    404 if template_id is not one of: negotiator, sourcing, contractor.
    """
    template = get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    return RoleTemplateResponse(**vars(template))
