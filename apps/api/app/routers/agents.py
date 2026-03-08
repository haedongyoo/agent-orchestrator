from __future__ import annotations
"""
Agents router — CRUD for agents + container management endpoints.

CRUD endpoints (all require Bearer JWT, workspace-ownership scoped):
  POST   /api/workspaces/{id}/agents               → 201 AgentResponse
  GET    /api/workspaces/{id}/agents               → 200 list[AgentResponse]
  PUT    /api/workspaces/{id}/agents/{aid}         → 200 AgentResponse  (partial update)
  DELETE /api/workspaces/{id}/agents/{aid}         → 204

Container management (requires Docker — tested in integration suite):
  GET    /api/workspaces/{id}/agents/{aid}/container         → ContainerStatusResponse
  POST   /api/workspaces/{id}/agents/{aid}/container/start   → 202 ContainerStatusResponse
  POST   /api/workspaces/{id}/agents/{aid}/container/stop    → 204

Security:
- All endpoints require an authenticated user (get_current_user).
- Workspace lookups filter by user_id — foreign workspaces return 404 (no leakage).
- allowed_tools validated against VALID_TOOLS allowlist.
- telegram_bot_token_ref is write-only (never returned in AgentResponse).
- ContainerManager imported lazily inside container endpoints to keep unit tests
  free of the Docker SDK dependency.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.agent import Agent
from app.models.workspace import User, Workspace
from app.services.auth import get_current_user

router = APIRouter()

# Allowlist of tools an agent may be granted.
VALID_TOOLS = frozenset({
    "send_email",
    "read_email_inbox",
    "send_telegram",
    "post_web_message",
    "request_approval",
    "upsert_vendor",
    "schedule_followup",
    "translate_message",
})


# ── Schemas ────────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role_prompt: str = Field(min_length=1, max_length=8192)
    allowed_tools: List[str] = Field(default_factory=list)
    telegram_bot_token_ref: Optional[str] = Field(default=None, max_length=512)
    rate_limit_per_min: int = Field(default=10, ge=1, le=600)
    max_concurrency: int = Field(default=3, ge=1, le=20)

    @field_validator("allowed_tools")
    @classmethod
    def validate_tools(cls, tools: List[str]) -> List[str]:
        invalid = set(tools) - VALID_TOOLS
        if invalid:
            raise ValueError(
                f"Unknown tool(s): {sorted(invalid)}. Valid tools: {sorted(VALID_TOOLS)}"
            )
        return tools


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role_prompt: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    allowed_tools: Optional[List[str]] = None
    telegram_bot_token_ref: Optional[str] = Field(default=None, max_length=512)
    is_enabled: Optional[bool] = None
    rate_limit_per_min: Optional[int] = Field(default=None, ge=1, le=600)
    max_concurrency: Optional[int] = Field(default=None, ge=1, le=20)

    @field_validator("allowed_tools")
    @classmethod
    def validate_tools(cls, tools: Optional[List[str]]) -> Optional[List[str]]:
        if tools is None:
            return tools
        invalid = set(tools) - VALID_TOOLS
        if invalid:
            raise ValueError(
                f"Unknown tool(s): {sorted(invalid)}. Valid tools: {sorted(VALID_TOOLS)}"
            )
        return tools


class AgentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    role_prompt: str
    allowed_tools: List[str]
    is_enabled: bool
    rate_limit_per_min: int
    max_concurrency: int
    has_telegram_token: bool = False
    # telegram_bot_token_ref intentionally excluded — write-only

    model_config = {"from_attributes": True}


class ContainerStatusResponse(BaseModel):
    agent_id: uuid.UUID
    status: str
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    image: Optional[str] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    last_status_check_at: Optional[str] = None
    exit_code: Optional[int] = None
    restart_count: int = 0


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_owned_workspace(
    workspace_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


async def _get_agent(
    workspace: Workspace,
    agent_id: uuid.UUID,
    db: AsyncSession,
) -> Agent:
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace.id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


def _agent_response(agent: Agent) -> AgentResponse:
    resp = AgentResponse.model_validate(agent)
    resp.has_telegram_token = bool(agent.telegram_bot_token_ref)
    return resp


# ── CRUD endpoints ─────────────────────────────────────────────────────────────

@router.post("/{workspace_id}/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: uuid.UUID,
    body: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Create a new agent in the workspace."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)

    agent = Agent(
        workspace_id=workspace.id,
        name=body.name,
        role_prompt=body.role_prompt,
        allowed_tools=body.allowed_tools,
        telegram_bot_token_ref=body.telegram_bot_token_ref,
        rate_limit_per_min=body.rate_limit_per_min,
        max_concurrency=body.max_concurrency,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _agent_response(agent)


@router.get("/{workspace_id}/agents", response_model=List[AgentResponse])
async def list_agents(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AgentResponse]:
    """List all agents in the workspace."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)

    result = await db.execute(
        select(Agent).where(Agent.workspace_id == workspace.id).order_by(Agent.created_at)
    )
    agents = result.scalars().all()
    return [_agent_response(a) for a in agents]


@router.put("/{workspace_id}/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Partially update an agent — only supplied fields are changed."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    agent = await _get_agent(workspace, agent_id, db)

    if body.name is not None:
        agent.name = body.name
    if body.role_prompt is not None:
        agent.role_prompt = body.role_prompt
    if body.allowed_tools is not None:
        agent.allowed_tools = body.allowed_tools
    if body.telegram_bot_token_ref is not None:
        agent.telegram_bot_token_ref = body.telegram_bot_token_ref
    if body.is_enabled is not None:
        agent.is_enabled = body.is_enabled
    if body.rate_limit_per_min is not None:
        agent.rate_limit_per_min = body.rate_limit_per_min
    if body.max_concurrency is not None:
        agent.max_concurrency = body.max_concurrency

    await db.commit()
    await db.refresh(agent)
    return _agent_response(agent)


@router.delete("/{workspace_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an agent and its associated container record (cascade)."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    agent = await _get_agent(workspace, agent_id, db)

    await db.delete(agent)
    await db.commit()


# ── Container management endpoints ─────────────────────────────────────────────
# Container start/stop are dispatched to the orchestrator-worker via Celery,
# because the API container does NOT have the Docker socket mounted.
# The orchestrator-worker has /var/run/docker.sock and runs ContainerManager.
# Status reads from the AgentContainer table (updated every 30s by beat task).

@router.get(
    "/{workspace_id}/agents/{agent_id}/container",
    response_model=ContainerStatusResponse,
    summary="Get container status for an agent",
)
async def get_container_status(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContainerStatusResponse:
    """Returns the current container status from DB (updated every 30s by monitor)."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    await _get_agent(workspace, agent_id, db)  # ownership check

    # Read from AgentContainer table — no Docker socket needed
    from app.models.container import AgentContainer
    result = await db.execute(
        select(AgentContainer).where(AgentContainer.agent_id == agent_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        return ContainerStatusResponse(agent_id=agent_id, status="no_container")

    return ContainerStatusResponse(
        agent_id=agent_id,
        status=record.status,
        container_id=record.container_id,
        container_name=record.container_name,
        image=record.image,
        started_at=record.started_at.isoformat() if record.started_at else None,
        stopped_at=record.stopped_at.isoformat() if record.stopped_at else None,
        last_status_check_at=(
            record.last_status_check_at.isoformat() if record.last_status_check_at else None
        ),
        exit_code=record.exit_code,
        restart_count=record.restart_count,
    )


@router.post(
    "/{workspace_id}/agents/{agent_id}/container/start",
    response_model=ContainerStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Spawn or restart a container for an agent",
)
async def start_container(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContainerStatusResponse:
    """Dispatch container start to orchestrator-worker (which has Docker socket)."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    agent = await _get_agent(workspace, agent_id, db)

    if not agent.is_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent is disabled — enable it first")

    # Dispatch to orchestrator-worker via Celery (it has Docker socket)
    from app.worker import celery_app
    celery_app.send_task(
        "app.tasks.container_ops.start_agent_container",
        args=[str(agent_id)],
        queue="orchestrator",
    )

    return ContainerStatusResponse(agent_id=agent_id, status="starting")


@router.post(
    "/{workspace_id}/agents/{agent_id}/container/stop",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ContainerStatusResponse,
    summary="Stop and remove an agent's container",
)
async def stop_container(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContainerStatusResponse:
    """Dispatch container stop to orchestrator-worker (which has Docker socket)."""
    workspace = await _get_owned_workspace(workspace_id, current_user, db)
    await _get_agent(workspace, agent_id, db)  # ownership check

    # Dispatch to orchestrator-worker via Celery
    from app.worker import celery_app
    celery_app.send_task(
        "app.tasks.container_ops.stop_agent_container",
        args=[str(agent_id)],
        queue="orchestrator",
    )

    return ContainerStatusResponse(agent_id=agent_id, status="stopping")
