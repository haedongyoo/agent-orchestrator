"""
Container Monitor — Celery beat task that keeps the orchestrator in sync
with the real state of agent Docker containers.

Runs every MONITOR_INTERVAL_SECONDS seconds.

For each non-stopped container it:
  1. Queries Docker API for current status
  2. Updates the agent_containers DB row
  3. Broadcasts a WebSocket event if status changed
  4. Auto-restarts crashed containers (up to MAX_AUTO_RESTARTS times)
"""
from __future__ import annotations

import asyncio
import structlog

from app.worker import celery_app
from app.db.session import AsyncSessionLocal
from app.services.container_manager import ContainerManager, MAX_AUTO_RESTARTS
from app.models.container import AgentContainer
from app.models.agent import Agent
from sqlalchemy import select

log = structlog.get_logger()

MONITOR_INTERVAL_SECONDS = 30  # configured in worker.py beat_schedule


@celery_app.task(name="app.tasks.container_monitor.refresh_all_containers")
def refresh_all_containers() -> dict:
    """
    Poll Docker for every active agent container and reconcile DB state.
    Triggered by Celery beat every MONITOR_INTERVAL_SECONDS.
    """
    log.info("container_monitor.start")
    results = asyncio.run(_run_refresh())
    log.info("container_monitor.done", checked=len(results))
    return {"checked": len(results), "results": results}


async def _run_refresh() -> list[dict]:
    async with AsyncSessionLocal() as db:
        manager = ContainerManager(db=db)
        updates = await manager.refresh_all()

        crashed_agents = []
        results = []

        for agent_id, new_status in updates:
            results.append({"agent_id": str(agent_id), "status": new_status})

            if new_status == "crashed":
                crashed_agents.append(agent_id)

        # Auto-restart crashed containers that are still within the retry limit
        for agent_id in crashed_agents:
            record_result = await db.execute(
                select(AgentContainer).where(AgentContainer.agent_id == agent_id)
            )
            record = record_result.scalar_one_or_none()

            if record and record.restart_count < MAX_AUTO_RESTARTS:
                log.warning(
                    "container_monitor.auto_restart",
                    agent_id=str(agent_id),
                    restart_count=record.restart_count,
                )
                restarted = await manager.restart(agent_id)
                if restarted:
                    # Broadcast container status change via WebSocket
                    await _broadcast_container_event(
                        workspace_id=str(record.workspace_id),
                        agent_id=str(agent_id),
                        event_type="container_restarted",
                        status="starting",
                        restart_count=restarted.restart_count,
                    )
            elif record and record.restart_count >= MAX_AUTO_RESTARTS:
                log.error(
                    "container_monitor.max_restarts_reached",
                    agent_id=str(agent_id),
                    restart_count=record.restart_count,
                )
                await _broadcast_container_event(
                    workspace_id=str(record.workspace_id),
                    agent_id=str(agent_id),
                    event_type="container_failed",
                    status="crashed",
                    restart_count=record.restart_count,
                )

        await db.commit()
        return results


async def _broadcast_container_event(
    workspace_id: str,
    agent_id: str,
    event_type: str,
    status: str,
    restart_count: int = 0,
) -> None:
    """Push a container status event to all WebSocket clients in the workspace."""
    # TODO: broadcast to workspace-level WebSocket channel
    # For now, log it. Will wire to webchat.broadcast() once workspace WS is implemented.
    log.info(
        "container_monitor.broadcast",
        workspace_id=workspace_id,
        agent_id=agent_id,
        event_type=event_type,
        status=status,
        restart_count=restart_count,
    )
