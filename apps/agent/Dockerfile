# ── Agent Runtime Image ────────────────────────────────────────────────────────
#
# SECURITY CONTRACT:
#   This container is intentionally network-isolated on agent-net.
#   It can reach:
#     - Redis (task queue only — via agent-net)
#     - Public internet (email/Telegram APIs — egress only)
#   It CANNOT reach:
#     - Postgres (not on agent-net)
#     - The API/Orchestrator service (not on agent-net)
#     - Other agent containers (no cross-container addressing allowed)
#
#   Agents communicate with the orchestrator exclusively through Redis queues.
#   DO NOT add backend-net to this container's network config.
#
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Agents run as a non-root user for an additional layer of isolation.
# chown -R ensures the agent user can write to /app (e.g. Celery temp files).
RUN useradd --create-home --shell /bin/bash agent \
    && chown -R agent:agent /app
USER agent

# Use shell form (not exec form) so $AGENT_ID is expanded from the environment
# at container startup. Exec form ["celery", ..., "agent.{AGENT_ID}"] would
# treat {AGENT_ID} as a literal string — not a shell variable.
CMD sh -c "celery -A agent_runtime.main worker \
    --loglevel=info \
    --queues=agent.${AGENT_ID:-placeholder-set-agent-id} \
    --concurrency=1"
