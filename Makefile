.PHONY: help up down restart build logs logs-api logs-worker logs-agent \
        migrate shell shell-agent test clean ps scale-agents

# ── Colours ────────────────────────────────────────────────────────────────────
CYAN  := \033[0;36m
RESET := \033[0m

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'

# ── Docker Compose ─────────────────────────────────────────────────────────────

up:  ## Start all services (detached)
	docker compose up -d

down:  ## Stop and remove containers
	docker compose down

restart:  ## Restart all services
	docker compose restart

build:  ## (Re)build all images
	docker compose build

ps:  ## Show running containers
	docker compose ps

# ── Logs ───────────────────────────────────────────────────────────────────────

logs:  ## Tail logs from api + workers
	docker compose logs -f api orchestrator-worker orchestrator-beat

logs-api:  ## Tail API logs only
	docker compose logs -f api

logs-worker:  ## Tail orchestrator worker logs
	docker compose logs -f orchestrator-worker orchestrator-beat

logs-agent:  ## Tail all agent-worker logs
	docker compose logs -f agent-worker

# ── Database ───────────────────────────────────────────────────────────────────

migrate:  ## Run Alembic migrations (upgrade head)
	docker compose --profile tools run --rm migrate

migrate-down:  ## Rollback one migration
	docker compose run --rm \
		-e DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/openclaw \
		api alembic downgrade -1

migrate-history:  ## Show migration history
	docker compose run --rm \
		-e DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/openclaw \
		api alembic history --verbose

# ── Shells ─────────────────────────────────────────────────────────────────────

shell:  ## Open a shell in the API container
	docker compose exec api bash

shell-agent:  ## Open a shell in the agent-worker container
	docker compose exec agent-worker bash

# ── Testing ────────────────────────────────────────────────────────────────────

test:  ## Run the full test suite inside the api container
	docker compose run --rm \
		-e DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/openclaw \
		api pytest apps/api/app/tests/ -v

test-policy:  ## Run policy engine tests only (fastest safety check)
	docker compose run --rm api pytest apps/api/app/tests/test_policy.py -v

# ── Agent scaling ──────────────────────────────────────────────────────────────

scale-agents:  ## Scale agent workers: make scale-agents N=3
	@if [ -z "$(N)" ]; then echo "Usage: make scale-agents N=<count>"; exit 1; fi
	docker compose up -d --scale agent-worker=$(N) agent-worker

# ── Cleanup ────────────────────────────────────────────────────────────────────

clean:  ## Remove containers, volumes, and built images (DESTRUCTIVE)
	@echo "WARNING: This will delete all local data (postgres, redis volumes)."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose down -v --rmi local

clean-images:  ## Remove only built images (keeps volumes)
	docker compose down --rmi local
