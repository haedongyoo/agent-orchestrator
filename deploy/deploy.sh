#!/usr/bin/env bash
# OpenClaw Agent Orchestrator — deployment script
# Runs on the Oracle Cloud VM via SSH (called by GitHub Actions or manually).
#
# Usage: ./deploy/deploy.sh [branch]
#   branch defaults to "main"

set -euo pipefail

BRANCH="${1:-main}"
APP_DIR="$HOME/agent-orchestrator"
COMPOSE_FILE="docker-compose.prod.yml"

echo "==> Deploying branch: $BRANCH"

# ── Clone or update repo ────────────────────────────────────────────────────
if [ ! -d "$APP_DIR" ]; then
    echo "==> Cloning repository..."
    git clone https://github.com/haedongyoo/agent-orchestrator.git "$APP_DIR"
fi

cd "$APP_DIR"
git fetch origin
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

# ── Ensure .env exists ──────────────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Create it from .env.example first."
    echo "  cp .env.example .env && nano .env"
    exit 1
fi

# ── Build images (native ARM on the VM) ─────────────────────────────────────
echo "==> Building Docker images..."
docker compose -f "$COMPOSE_FILE" build --parallel

# ── Deploy ──────────────────────────────────────────────────────────────────
echo "==> Stopping old containers..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans

echo "==> Starting services..."
docker compose -f "$COMPOSE_FILE" up -d

# ── Wait for API health ────────────────────────────────────────────────────
echo "==> Waiting for API to be healthy..."
for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" exec -T api curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "==> API is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: API failed to become healthy after 30 attempts"
        docker compose -f "$COMPOSE_FILE" logs api --tail 50
        exit 1
    fi
    sleep 2
done

# ── Run migrations ─────────────────────────────────────────────────────────
echo "==> Running database migrations..."
docker compose -f "$COMPOSE_FILE" --profile tools run --rm migrate

# ── Cleanup ────────────────────────────────────────────────────────────────
echo "==> Pruning old Docker images..."
docker image prune -f

echo "==> Deployment complete!"
docker compose -f "$COMPOSE_FILE" ps
