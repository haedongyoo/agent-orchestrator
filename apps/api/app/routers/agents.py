from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.db.session import get_db
from app.services.container_manager import ContainerManager

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    role_prompt: str
    allowed_tools: List[str] = []
    telegram_bot_token_ref: Optional[str] = None  # vault/kms ref, not the raw token
    rate_limit_per_min: int = 10
    max_concurrency: int = 3


class AgentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    role_prompt: str
    allowed_tools: List[str]
    is_enabled: bool
    rate_limit_per_min: int
    max_concurrency: int

    class Config:
        from_attributes = True


class ContainerStatusResponse(BaseModel):
    agent_id: uuid.UUID
    status: str                         # starting | running | stopped | crashed | unknown | no_container
    container_id: Optional[str]         # full Docker container hash (64 chars)
    container_name: Optional[str]       # openclaw-agent-{agent_id}
    image: Optional[str]
    started_at: Optional[str]
    stopped_at: Optional[str]
    last_status_check_at: Optional[str]
    exit_code: Optional[int]
    restart_count: int = 0


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/{workspace_id}/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(workspace_id: uuid.UUID, body: AgentCreate, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{workspace_id}/agents", response_model=List[AgentResponse])
async def list_agents(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/{workspace_id}/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(workspace_id: uuid.UUID, agent_id: uuid.UUID, body: AgentCreate, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/{workspace_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(workspace_id: uuid.UUID, agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Container management endpoints ─────────────────────────────────────────────

@router.get(
    "/{workspace_id}/agents/{agent_id}/container",
    response_model=ContainerStatusResponse,
    summary="Get container status for an agent",
)
async def get_container_status(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the current Docker container status for an agent.
    Reads from the agent_containers DB table (updated every 30s by the monitor).
    """
    manager = ContainerManager(db=db)
    info = await manager.get_status(agent_id)
    return ContainerStatusResponse(agent_id=agent_id, **info)


@router.post(
    "/{workspace_id}/agents/{agent_id}/container/start",
    response_model=ContainerStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Spawn or restart a container for an agent",
)
async def start_container(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Spawn a new Docker container for the agent.
    If the agent already has a running container it is stopped first.
    The agent must be enabled (is_enabled=True).
    """
    from app.models.agent import Agent
    agent = await db.get(Agent, agent_id)
    if not agent or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.is_enabled:
        raise HTTPException(status_code=400, detail="Agent is disabled — enable it first")

    manager = ContainerManager(db=db)
    try:
        record = await manager.spawn(agent)
        await db.commit()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    info = await manager.get_status(agent_id)
    return ContainerStatusResponse(agent_id=agent_id, **info)


@router.post(
    "/{workspace_id}/agents/{agent_id}/container/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop and remove an agent's container",
)
async def stop_container(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stop and remove the Docker container for an agent."""
    manager = ContainerManager(db=db)
    await manager.stop(agent_id)
    await db.commit()
