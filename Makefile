.PHONY: help up down restart build logs logs-api logs-worker logs-agent logs-web \
        migrate migrate-down migrate-history shell shell-agent \
        test test-policy scale-agents clean clean-images \
        dev-web \
        prod-build prod-up prod-down prod-migrate prod-logs

# ── Colours ────────────────────────────────────────────────────────────────────
CYAN  := \033[0;36m
RESET := \033[0m

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-22s$(RESET) %s\n", $$1, $$2}'

# ── Development ─────────────────────────────────────────────────────────────────

up:  ## Start all dev services (detached)
	docker compose up -d

down:  ## Stop and remove dev containers
	docker compose down

restart:  ## Restart all dev services
	docker compose restart

build:  ## (Re)build all dev images (including agent runtime)
	docker compose --profile agent-dev build

build-agent:  ## Build only the agent runtime image
	docker compose --profile agent-dev build agent-worker

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

logs-web:  ## Tail web UI logs
	docker compose logs -f web

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
		api pytest app/tests/ -v

test-policy:  ## Run policy engine tests only (fastest safety check)
	docker compose run --rm api pytest app/tests/test_policy.py -v

# ── Agent scaling ──────────────────────────────────────────────────────────────

scale-agents:  ## Scale agent workers: make scale-agents N=3
	@if [ -z "$(N)" ]; then echo "Usage: make scale-agents N=<count>"; exit 1; fi
	docker compose --profile agent-dev up -d --scale agent-worker=$(N) agent-worker

# ── Web UI ────────────────────────────────────────────────────────────────────

dev-web:  ## Run web UI locally (not in Docker — uses npm run dev)
	cd apps/web && npm run dev

# ── Production ─────────────────────────────────────────────────────────────────

prod-build:  ## Build production images (including agent runtime)
	docker compose -f docker-compose.prod.yml --profile agent-dev build --parallel

prod-up:  ## Start production stack (detached)
	docker compose -f docker-compose.prod.yml up -d

prod-down:  ## Stop production stack
	docker compose -f docker-compose.prod.yml down

prod-migrate:  ## Run Alembic migrations against production DB
	docker compose -f docker-compose.prod.yml --profile tools run --rm migrate

prod-logs:  ## Tail all production logs
	docker compose -f docker-compose.prod.yml logs -f

prod-logs-api:  ## Tail production API + worker logs
	docker compose -f docker-compose.prod.yml logs -f api orchestrator-worker orchestrator-beat

prod-logs-web:  ## Tail production web UI logs
	docker compose -f docker-compose.prod.yml logs -f web

prod-logs-caddy:  ## Tail Caddy reverse proxy logs
	docker compose -f docker-compose.prod.yml logs -f caddy

prod-ps:  ## Show production container status
	docker compose -f docker-compose.prod.yml ps

prod-deploy:  ## Full deploy: build + restart + migrate
	bash deploy/deploy.sh

# ── Cleanup ────────────────────────────────────────────────────────────────────

clean:  ## Remove containers, volumes, and built images (DESTRUCTIVE)
	@echo "WARNING: This will delete all local data (postgres, redis volumes)."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose down -v --rmi local

clean-images:  ## Remove only built images (keeps volumes)
	docker compose down --rmi local
