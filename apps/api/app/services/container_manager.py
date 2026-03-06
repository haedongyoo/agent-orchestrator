"""
ContainerManager — manages the lifecycle of per-agent Docker containers.

Responsibilities:
  - Spawn a new container when an agent is enabled
  - Stop/remove a container when an agent is disabled or deleted
  - Restart a crashed container (with exponential backoff via restart_count)
  - Refresh status by querying the Docker API
  - Provide a bulk refresh for the container_monitor beat task

Docker calls are synchronous (docker-py is blocking).
DB calls are async (SQLAlchemy async session).
Celery tasks call this via asyncio.run() in a sync worker.

Security: The orchestrator container must have /var/run/docker.sock mounted.
Agent containers are ALWAYS spawned onto agent-net only — never backend-net.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import docker
import docker.errors
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent import Agent
from app.models.container import AgentContainer
from app.models.llm_config import LLMConfig
from app.models.base import utcnow

log = structlog.get_logger()

# Maximum auto-restarts before giving up and leaving status as "crashed"
MAX_AUTO_RESTARTS = 5


class ContainerNotFound(Exception):
    pass


class ContainerManager:
    def __init__(self, db: AsyncSession, docker_client=None):
        self.db = db
        self._docker = docker_client  # injected in tests; lazy-loaded in prod

    # ── Docker client (lazy) ───────────────────────────────────────────────────

    @property
    def docker(self):
        if self._docker is None:
            self._docker = docker.from_env()
        return self._docker

    # ── Public interface ───────────────────────────────────────────────────────

    async def spawn(self, agent: Agent) -> AgentContainer:
        """
        Start a Docker container for the given agent.

        If a container record already exists for this agent, it is updated
        in-place (e.g. after a restart). Otherwise a new record is created.
        Returns the up-to-date AgentContainer record.
        """
        container_name = f"openclaw-agent-{agent.id}"
        image = settings.docker_agent_image

        log.info("container_manager.spawn", agent_id=str(agent.id), image=image)

        # Resolve LLM config: agent override → workspace default → env var fallback
        llm_env = await self._resolve_llm_env(agent)

        # Stop any existing container for this agent before spawning a new one
        existing = await self._get_record(agent.id)
        if existing and existing.container_id:
            self._stop_docker_container(existing.container_id, remove=True)

        # Spawn the new container (sync Docker call)
        container_id = self._run_container(
            agent_id=str(agent.id),
            container_name=container_name,
            image=image,
            llm_env=llm_env,
        )

        # Persist / update the record
        if existing:
            existing.container_id = container_id
            existing.container_name = container_name
            existing.image = image
            existing.status = "starting"
            existing.started_at = utcnow()
            existing.stopped_at = None
            existing.exit_code = None
            existing.error_message = None
            existing.restart_count = existing.restart_count + 1
            record = existing
        else:
            record = AgentContainer(
                agent_id=agent.id,
                workspace_id=agent.workspace_id,
                container_id=container_id,
                container_name=container_name,
                image=image,
                status="starting",
                started_at=utcnow(),
                restart_count=0,
            )
            self.db.add(record)

        await self.db.flush()
        log.info(
            "container_manager.spawned",
            agent_id=str(agent.id),
            container_id=container_id[:12],
        )
        return record

    async def stop(self, agent_id: uuid.UUID, remove: bool = True) -> None:
        """Stop (and optionally remove) the container for this agent."""
        record = await self._get_record(agent_id)
        if not record or not record.container_id:
            log.warning("container_manager.stop.no_record", agent_id=str(agent_id))
            return

        log.info("container_manager.stop", agent_id=str(agent_id), container_id=record.container_id[:12])
        self._stop_docker_container(record.container_id, remove=remove)

        record.status = "stopped"
        record.stopped_at = utcnow()
        await self.db.flush()

    async def restart(self, agent_id: uuid.UUID) -> Optional[AgentContainer]:
        """
        Restart a crashed container if auto-restart limit has not been reached.
        Returns the updated record, or None if the limit was hit.
        """
        record = await self._get_record(agent_id)
        if not record:
            return None

        if record.restart_count >= MAX_AUTO_RESTARTS:
            log.error(
                "container_manager.restart.limit_reached",
                agent_id=str(agent_id),
                restart_count=record.restart_count,
            )
            return None

        # Fetch agent to pass to spawn
        agent = await self.db.get(Agent, agent_id)
        if not agent or not agent.is_enabled:
            return None

        log.info(
            "container_manager.restart",
            agent_id=str(agent_id),
            restart_count=record.restart_count,
        )
        return await self.spawn(agent)

    async def refresh_status(self, record: AgentContainer) -> str:
        """
        Query Docker for the current status of one container and update the DB.
        Returns the new status string.
        """
        if not record.container_id:
            return "unknown"

        docker_status, exit_code = self._inspect_container(record.container_id)
        new_status = _docker_status_to_model(docker_status, exit_code)

        changed = record.status != new_status
        record.status = new_status
        record.last_status_check_at = utcnow()

        if exit_code is not None:
            record.exit_code = exit_code
        if new_status == "stopped" and record.stopped_at is None:
            record.stopped_at = utcnow()

        await self.db.flush()

        if changed:
            log.info(
                "container_manager.status_changed",
                agent_id=str(record.agent_id),
                container_id=record.container_id[:12],
                new_status=new_status,
            )

        return new_status

    async def refresh_all(self) -> list[tuple[uuid.UUID, str]]:
        """
        Refresh status for all non-stopped containers.
        Returns list of (agent_id, new_status) for changed records.
        Returns results for all checked containers (changed or not).
        """
        result = await self.db.execute(
            select(AgentContainer).where(
                AgentContainer.status.in_(["starting", "running", "unknown"])
            )
        )
        records = result.scalars().all()

        updates = []
        for record in records:
            new_status = await self.refresh_status(record)
            updates.append((record.agent_id, new_status))

        return updates

    async def get_status(self, agent_id: uuid.UUID) -> dict:
        """
        Return a status dict for the agent's container.
        Used by the API router for GET /agents/{id}/container.
        """
        record = await self._get_record(agent_id)
        if not record:
            return {"status": "no_container", "container_id": None}

        return {
            "status": record.status,
            "container_id": record.container_id,
            "container_name": record.container_name,
            "image": record.image,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "stopped_at": record.stopped_at.isoformat() if record.stopped_at else None,
            "last_status_check_at": (
                record.last_status_check_at.isoformat() if record.last_status_check_at else None
            ),
            "exit_code": record.exit_code,
            "restart_count": record.restart_count,
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_record(self, agent_id: uuid.UUID) -> Optional[AgentContainer]:
        result = await self.db.execute(
            select(AgentContainer).where(AgentContainer.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def _resolve_llm_env(self, agent: Agent) -> dict[str, str]:
        """
        Resolve LLM config for this agent from DB, decrypting the API key.

        Priority:
          1. Agent-level override (LLMConfig with agent_id = agent.id)
          2. Workspace default   (LLMConfig with agent_id = None)
          3. Env var fallback    (LLM_MODEL / LLM_API_KEY from docker-compose)

        Returns a dict of env vars to inject into the container.
        """
        from app.services.secrets import decrypt_api_key

        # Agent override first
        result = await self.db.execute(
            select(LLMConfig).where(
                LLMConfig.workspace_id == agent.workspace_id,
                LLMConfig.agent_id == agent.id,
                LLMConfig.is_active == True,  # noqa: E712
            )
        )
        cfg = result.scalar_one_or_none()

        # Fall back to workspace default
        if not cfg:
            result = await self.db.execute(
                select(LLMConfig).where(
                    LLMConfig.workspace_id == agent.workspace_id,
                    LLMConfig.agent_id == None,  # noqa: E711
                    LLMConfig.is_active == True,  # noqa: E712
                )
            )
            cfg = result.scalar_one_or_none()

        if not cfg:
            # Fall back to env vars set in docker-compose — no DB config needed for dev
            log.debug(
                "container_manager.llm_config.using_env_fallback",
                agent_id=str(agent.id),
            )
            return {}  # runner reads LLM_MODEL etc. from its own env

        env: dict[str, str] = {
            "LLM_MODEL":      cfg.model,
            "LLM_MAX_TOKENS": str(cfg.max_tokens),
        }
        if cfg.api_base_url:
            env["LLM_API_BASE"] = cfg.api_base_url
        if cfg.api_key_encrypted:
            try:
                env["LLM_API_KEY"] = decrypt_api_key(cfg.api_key_encrypted)
            except ValueError:
                log.error(
                    "container_manager.llm_config.decrypt_failed",
                    agent_id=str(agent.id),
                    llm_config_id=str(cfg.id),
                )

        log.info(
            "container_manager.llm_config.resolved",
            agent_id=str(agent.id),
            model=cfg.model,
            source="agent_override" if cfg.agent_id else "workspace_default",
        )
        return env

    def _run_container(
        self,
        agent_id: str,
        container_name: str,
        image: str,
        llm_env: Optional[dict[str, str]] = None,
    ) -> str:
        """Sync Docker call — returns the full container ID."""
        try:
            # Remove any existing stopped container with this name
            try:
                old = self.docker.containers.get(container_name)
                old.remove(force=True)
            except docker.errors.NotFound:
                pass

            environment = {
                "AGENT_ID":  agent_id,
                "REDIS_URL": settings.redis_url,
                **(llm_env or {}),   # DB-resolved LLM config takes precedence over image defaults
            }

            container = self.docker.containers.run(
                image=image,
                name=container_name,
                environment=environment,
                network=settings.docker_agent_network,
                detach=True,
                restart_policy={"Name": "no"},  # orchestrator handles restarts
                labels={
                    "openclaw.agent_id": agent_id,
                    "openclaw.managed":  "true",
                },
            )
            return container.id
        except docker.errors.ImageNotFound:
            raise RuntimeError(
                f"Agent image '{image}' not found. Run `make build` first."
            )
        except docker.errors.APIError as e:
            raise RuntimeError(f"Docker API error spawning agent {agent_id}: {e}")

    def _stop_docker_container(self, container_id: str, remove: bool = True) -> None:
        """Sync Docker call — stops and optionally removes a container."""
        try:
            container = self.docker.containers.get(container_id)
            container.stop(timeout=10)
            if remove:
                container.remove()
        except docker.errors.NotFound:
            pass  # already gone
        except docker.errors.APIError as e:
            log.warning("container_manager.stop_error", container_id=container_id[:12], error=str(e))

    # Make this a regular method, not async, since it's a sync Docker call
    def _inspect_container(self, container_id: str) -> tuple[str, Optional[int]]:
        """
        Sync Docker call.
        Returns (docker_status_str, exit_code_or_none).
        docker_status values: "running", "exited", "paused", "restarting", "dead", "created"
        """
        try:
            container = self.docker.containers.get(container_id)
            container.reload()
            state = container.attrs.get("State", {})
            docker_status = state.get("Status", "unknown")
            exit_code = state.get("ExitCode") if docker_status in ("exited", "dead") else None
            return docker_status, exit_code
        except docker.errors.NotFound:
            return "not_found", None
        except docker.errors.APIError:
            return "unknown", None


def _docker_status_to_model(docker_status: str, exit_code: Optional[int]) -> str:
    """Map Docker container status strings to our model's status enum."""
    mapping = {
        "running": "running",
        "created": "starting",
        "restarting": "starting",
        "paused": "running",       # paused is still "alive"
        "exited": "stopped" if exit_code == 0 else "crashed",
        "dead": "crashed",
        "not_found": "unknown",
        "unknown": "unknown",
    }
    if docker_status == "exited":
        return "stopped" if (exit_code or 0) == 0 else "crashed"
    return mapping.get(docker_status, "unknown")
