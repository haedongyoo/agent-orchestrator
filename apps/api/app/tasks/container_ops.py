"""
Container Operations — Celery tasks for starting/stopping agent containers.

These tasks run on the orchestrator-worker which has the Docker socket mounted.
The API service dispatches to these tasks instead of calling ContainerManager
directly, since the API container does NOT have access to the Docker socket.

Flow:
  UI clicks "Start Container"
    → POST /api/.../container/start (API service)
    → celery_app.send_task("app.tasks.container_ops.start_agent_container")
    → orchestrator-worker (HAS Docker socket)
    → ContainerManager.spawn(agent)
    → AgentContainer record updated in DB
"""
from __future__ import annotations

import asyncio
import uuid

import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.container_ops.start_agent_container",
    queue="orchestrator",
)
def start_agent_container(agent_id: str) -> dict:
    """Start (or restart) a container for the given agent."""
    log.info("container_ops.start", agent_id=agent_id)
    return asyncio.run(_start(agent_id))


async def _start(agent_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.models.agent import Agent
    from app.services.container_manager import ContainerManager

    async with AsyncSessionLocal() as db:
        agent = await db.get(Agent, uuid.UUID(agent_id))
        if not agent:
            return {"success": False, "error": "Agent not found"}
        if not agent.is_enabled:
            return {"success": False, "error": "Agent is disabled"}

        manager = ContainerManager(db=db)
        try:
            record = await manager.spawn(agent)
            await db.commit()
            return {
                "success": True,
                "container_id": record.container_id,
                "status": record.status,
            }
        except RuntimeError as exc:
            log.error("container_ops.start.failed", agent_id=agent_id, error=str(exc))
            return {"success": False, "error": str(exc)}


@celery_app.task(
    name="app.tasks.container_ops.stop_agent_container",
    queue="orchestrator",
)
def stop_agent_container(agent_id: str) -> dict:
    """Stop and remove the container for the given agent."""
    log.info("container_ops.stop", agent_id=agent_id)
    return asyncio.run(_stop(agent_id))


async def _stop(agent_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.container_manager import ContainerManager

    async with AsyncSessionLocal() as db:
        manager = ContainerManager(db=db)
        await manager.stop(uuid.UUID(agent_id))
        await db.commit()
        return {"success": True}
