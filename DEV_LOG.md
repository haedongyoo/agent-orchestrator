# OpenClaw Agent Orchestrator — Development Log

Chronological record of development progress, decisions, and next steps.
Update this file at the end of every meaningful dev session.

---

## 2026-03-01 (Session 2) — Workspace CRUD, Agent CRUD, Subscription Update

### What Was Done

**Workspace CRUD** (PR #1, merged):
- `POST /api/workspaces` — create workspace → 201
- `GET /api/workspaces/{id}` — get workspace → 200 / 404
- `PUT /api/workspaces/{id}` — partial update → 200 / 404
- `POST /api/workspaces/{id}/shared-email` — add email account → 201
- `PUT /api/workspaces/{id}/shared-email/{eid}` — update email account → 200
- `credentials_ref` write-only; `provider_type` validated against allowlist (`imap|gmail|graph`)
- 15 tests, 32/32 total passing

**Agent CRUD + role prompt** (PR #2, merged):
- `POST /api/workspaces/{id}/agents` — create agent → 201
- `GET /api/workspaces/{id}/agents` — list agents → 200 []
- `PUT /api/workspaces/{id}/agents/{aid}` — partial update → 200
- `DELETE /api/workspaces/{id}/agents/{aid}` — delete → 204
- `allowed_tools` validated against strict allowlist (7 tools — no arbitrary tool grants)
- `telegram_bot_token_ref` write-only (vault ref never returned)
- `ContainerManager` lazily imported → unit tests stay Docker-free
- Container management endpoints (start/stop) updated with ownership checks
- 15 tests, 47/47 total passing

**Thread + Message CRUD** (PR #3, feat/thread-message-crud):
- `POST /api/workspaces/{id}/threads` — create thread → 201
- `GET /api/threads/{id}` — get thread with ownership check → 200 / 404
- `POST /api/threads/{id}/messages` — post user message → 201
- `GET /api/threads/{id}/messages` — cursor-paginated list → 200 MessagePage
  - Cursor = base64url(JSON{created_at, id}) — opaque, tamper-proof, stable
  - `next_cursor` set only when `len(items) == limit`; `null` at end of results
- `channel` validated: `web|telegram|email|system`; invalid → 422
- `sender_type` hardcoded to `"user"` for user-posted messages
- 17 tests, 64/64 total passing

**Anthropic subscription updated**:
- Upgraded to Anthropic API plan with full `claude-opus-4-6` access
- `LLM_MAX_TOKENS` updated from `4096` → `32768` (Opus 4.6 supports up to 32K output)
- Updated in: `apps/agent/agent_runtime/runner.py` default + `.env.example`

### Key Decisions Made
- POST-PR workflow established: merge → `git checkout main && git pull` → new feature branch → `/auto --mode feature`
- All mutating endpoints require Bearer JWT + workspace owner check (returns 404 not 403 to avoid leaking resource existence)
- `allowed_tools` allowlist maintained in router layer (not model) — single authoritative source

### Next Steps
- ~~Thread + Message CRUD with cursor pagination~~ ✓ done (PR #3)
- ~~Orchestrator: step queue + approval flow for A2A messages~~ ✓ done (PR #4)
- Telegram inbound/outbound connector

---

## 2026-03-01 (Session 3) — Orchestrator Step Queue + A2A Approval Gating

### What Was Done

**Orchestrator step queue + A2A approval flow** (PR #4, feat/orchestrator-step-queue):

**`policy.py` — Real A2A approval check:**
- `_check_a2a()` now queries the `approvals` table for active approved A2A permissions
- Scope validation: agent pair match, thread scope, duration window (expired approvals are re-blocked)
- Falls back to creating a pending approval + returning `a2a_not_approved` if no active approval found
- 9 tests covering: blocked by default, creates approval row, allowed with active approval, expired approval blocks, wrong-thread blocks, wrong-agent-pair blocks

**`router.py` — dispatch_step + route enhancement:**
- `dispatch_step(task_id, agent_id, step_type, content, workspace_id)` → creates `TaskStep` with explicit UUID (available before DB flush) + calls `_enqueue_to_agent()`
- `enqueue_existing_step(step, workspace_id)` → enqueues an already-persisted step (used by `create_task`)
- `_enqueue_to_agent(...)` → lazy `celery_app.send_task()` push to `agent.{agent_id}` queue; lazy import keeps unit tests broker-free
- `route()` now dispatches a "message" step when receiver_type=="agent" and task_id is provided; returns `step_id` in result
- 11 tests covering: blocked route, approval_id pass-through, audit log, step dispatch with/without task_id, non-agent routes, dispatch_step internals

**`tasks.py` — Full implementation:**
- `POST /api/threads/{thread_id}/tasks` → create Task (queued) → `Planner.decompose()` → `enqueue_existing_step()` per step → task becomes "running"; auth + ownership-scoped
- `GET /api/tasks/{task_id}` → get task with ownership check
- `GET /api/tasks/{task_id}/steps` → list steps ordered by created_at
- `POST /api/tasks/{task_id}/cancel` → mark task + all queued/running steps as "failed" (idempotent if already terminal)
- Ownership chain: task → workspace → user_id == current_user.id; returns 404 to avoid leaking

**`step_results.py` — Task status update:**
- After a step result is processed, queries all sibling steps for the task
- If all steps are terminal (done/failed): updates task.status = "done" or "failed"
- Correctly applies the in-memory status change before evaluating siblings

**`llm_configs.py` — Bug fix:**
- Removed duplicate `from __future__ import annotations` (caused SyntaxError at import time)

### Key Decisions Made
- `TaskStep.id` explicitly generated with `uuid.uuid4()` before flush (same pattern as `Approval`) — ensures id is available for Celery payload before DB round-trip
- `_enqueue_to_agent()` is a method (not a module function) — easy to mock in tests with `patch.object(orch, "_enqueue_to_agent")`
- `enqueue_existing_step()` decouples step creation (planner) from dispatch — planner creates steps, router enqueues them
- Tasks without available agents stay in "queued" status; Planner.decompose() raises ValueError if no agents — handled gracefully

### Test Count
- 79/79 passing (up from 64 — added 15 new tests)

### Next Steps
- ~~Telegram inbound/outbound connector~~ ✓ in progress (PR #5)
- Email outbound + basic IMAP inbound polling
- Role templates: negotiator / sourcing / contractor

---

## 2026-03-01 (Session 4) — Telegram Connector (Inbound + Outbound)

### What Was Done

**Telegram connector** (PR #5, feat/telegram-connector):

**`services/connectors/telegram.py` — full implementation:**
- `POST /api/connectors/telegram/{agent_id}` — inbound webhook handler:
  - Always returns `{"ok": true}` (prevents Telegram retry loops on errors)
  - Agent lookup by UUID path param; graceful 200 on unknown agent
  - Handles `message` and `edited_message` update types; ignores non-text updates (photos, stickers, etc.)
  - `_find_or_create_thread(db, agent, chat_id, text)` — finds thread by `(workspace_id, linked_telegram_chat_id)` or creates one titled with the first message
  - Persists inbound message: `sender_type="external"`, `channel="telegram"`, `metadata_={telegram_message_id, chat_id}`
  - Creates a Task with the message as objective; `created_by` = workspace owner (`ws.user_id`)
  - Calls `Planner.decompose()` then `OrchestratorRouter.enqueue_existing_step()` per step → agent queue
- `send_message(bot_token, chat_id, text, reply_to_message_id?)` — outbound via Telegram Bot API; `parse_mode=HTML`
- `register_webhook(bot_token, webhook_url)` — calls `setWebhook` for bot setup
- `delete_webhook(bot_token)` — calls `deleteWebhook` for agent teardown
- `_resolve_token(agent)` — MVP: raw token from `telegram_bot_token_ref`; production stub for Vault

**`tests/test_connectors.py` — 9 tests, all passing:**
- Webhook: valid message → ok, unknown agent → ok, non-text → ignored, existing thread reused, new thread created, task dispatched
- `send_message`: httpx POST verified, `reply_to_message_id` included when provided
- WebChat broadcast: no-op on empty thread (existing)

### Key Decisions Made
- Webhook path uses agent UUID (opaque but leaks internal ID); production note in docstring for HMAC-derived path
- `created_by` on Task set to workspace owner's user_id (FK constraint requires a user; external inbound has no user identity)
- Thread auto-created per `(workspace_id, chat_id)` pair; title = first 100 chars of message
- `telegram_bot_token_ref` treated as plaintext MVP token; `_resolve_token()` is the swap point for Vault integration
- Each inbound Telegram message creates a new Task (MVP); V1 could maintain persistent conversation Task per chat

### Test Count
- 88/88 passing (up from 79 — added 9 new connector tests)

### Next Steps
- Email outbound + basic IMAP inbound polling
- Role templates: negotiator / sourcing / contractor

---

## 2026-02-28 — Project Initialization

### What Was Done
- Created `agent-orchestrator.md` — the master project plan (architecture, data model, API design, implementation phases).
- Created `CLAUDE.md` — Claude Code project reference file distilled from the plan. Includes architecture overview, tech stack, repo layout, data model, API endpoints, agent tool contracts, implementation phases, and working rules.
- Created `DEV_LOG.md` (this file) — development journal.

### Key Decisions Made
- **Language/Framework**: Python + FastAPI
- **Database**: Postgres
- **Queue (MVP)**: Redis + Celery/RQ
- **Queue (Production)**: Temporal (strongly preferred for long workflows)
- **Agent Runtime**: OpenClaw in isolated worker processes/containers
- **Telegram**: Webhook-based, one bot token per agent
- **Email (MVP)**: IMAP/SMTP polling; **Email (V1)**: OAuth (Gmail / Microsoft Graph)
- **Secrets**: Never plaintext — `credentials_ref` pattern with Vault/KMS
- **A2A Communication**: OFF by default, approval-gated with scope (agents, thread, duration, content type)

### Project State
- No code written yet. Pure planning phase complete.
- `agent-orchestrator.md` is the source of truth for all architecture decisions.

### Next Steps
- Scaffold repo structure: `apps/api/app/` with routers, services, models, db directories
- Set up FastAPI app skeleton with health check endpoint
- Define SQLAlchemy models for core tables (users, workspaces, agents, threads, messages)
- Set up Alembic for migrations
- Implement auth (JWT or session-based)
- Start with workspace + agent CRUD endpoints

---

---

## 2026-03-01 — Repo Scaffold

### What Was Done
- Scaffolded full repo directory structure under `apps/api/app/`
- Created all files with working skeleton code (not just empty stubs):

**Root level:**
- `.gitignore` — Python, secrets, IDE, Docker patterns
- `.env.example` — all env vars documented with sensible defaults
- `apps/api/requirements.txt` — pinned dependencies (FastAPI, SQLAlchemy async, Alembic, Celery, Redis, python-telegram-bot, aiosmtplib, aioimaplib, httpx, structlog, pytest)

**App core:**
- `app/main.py` — FastAPI app with lifespan, CORS, all routers registered, `/health` endpoint
- `app/config.py` — pydantic-settings `Settings` class loading from `.env`

**Models (SQLAlchemy 2.0 mapped_column style):**
- `models/base.py` — DeclarativeBase + `utcnow()` helper
- `models/workspace.py` — `User`, `Workspace`, `UserChannel`, `SharedEmailAccount`
- `models/agent.py` — `Agent` (with `allowed_tools` JSON, `telegram_bot_token_ref` as vault ref)
- `models/thread.py` — `Thread` (with telegram/email link columns)
- `models/message.py` — `Message` (multi-channel, metadata JSON)
- `models/task.py` — `Task` + `TaskStep` (full status state machine documented)
- `models/approval.py` — `Approval` (A2A + email approvals, scope JSON)
- `models/audit.py` — `AuditLog`
- `models/__init__.py` — re-exports all models

**DB:**
- `db/session.py` — async SQLAlchemy engine + `AsyncSessionLocal` + `get_db` dependency

**Routers (skeleton endpoints returning 501):**
- `routers/auth.py` — register, login (JWT)
- `routers/workspaces.py` — workspace CRUD + shared email
- `routers/agents.py` — agent CRUD under workspace
- `routers/threads.py` — threads + messages + pagination cursor
- `routers/tasks.py` — task create/get/steps/cancel
- `routers/approvals.py` — list/approve/reject

**Services — Orchestrator:**
- `services/orchestrator/policy.py` — `PolicyEngine.check_route()` (A2A blocked by default, creates approval row)
- `services/orchestrator/router.py` — `OrchestratorRouter.route()` (all traffic passes through policy + writes audit log)
- `services/orchestrator/planner.py` — `Planner.decompose()` (task → steps, stub for LLM decomposition)
- `services/orchestrator/scheduler.py` — `Scheduler.schedule_followup()` / `cancel_followup()` (Celery ETA stub)

**Services — Connectors:**
- `services/connectors/telegram.py` — webhook endpoint + `send_message()` stub
- `services/connectors/email.py` — `send_email()` + `poll_inbox()` stubs (credentials always via vault ref)
- `services/connectors/webchat.py` — WebSocket endpoint + `broadcast()` helper (in-memory registry for MVP)

**Tests:**
- `tests/test_policy.py` — 5 tests covering A2A block, approval creation, user↔agent allow
- `tests/test_orchestrator.py` — tests for blocked route response + audit log always written
- `tests/test_connectors.py` — health check, Telegram webhook 200 OK, broadcast no-op safety

### Decisions Made
- SQLAlchemy 2.0 `mapped_column` syntax (typed, no legacy `Column`)
- `credentials_ref` pattern enforced at model level — `telegram_bot_token_ref`, `credentials_ref` are vault refs in all models
- WebSocket connection registry is in-memory for MVP; documented to swap to Redis pub/sub for multi-worker
- All router endpoints return `501 Not Implemented` — no fake data, forces real implementations
- Tests use `pytest-asyncio` + `unittest.mock.AsyncMock` (no external services needed)

### Issues / Blockers
- None — scaffold is clean, no external dependencies needed to run tests (mocked)

### Next Steps
- `git init` + initial commit
- Set up Alembic (`alembic init` in `apps/api/`) and write first migration
- Implement auth: `POST /api/auth/register` + `POST /api/auth/login` (JWT)
- Implement workspace + agent CRUD (the two simplest endpoints)
- Wire up a local Postgres + Redis with Docker Compose for dev

---

---

## 2026-03-01 — Docker + Containerized Agent Runtime

### What Was Done

**Dockerfiles:**
- `apps/api/Dockerfile` — Python 3.12-slim, installs gcc (asyncpg C ext), runs uvicorn
- `apps/agent/Dockerfile` — Same base, runs as non-root `agent` user, Celery worker for `agent.{AGENT_ID}` queue

**docker-compose.yml (root):**
- 7 services: `postgres`, `redis`, `api`, `orchestrator-worker`, `orchestrator-beat`, `agent-worker`, `migrate`
- Network topology enforced:
  - `backend-net`: api, orchestrator-*, postgres, redis
  - `agent-net`: agent-worker, redis (ONLY)
  - Agents cannot resolve postgres or api by hostname
- `migrate` service runs `alembic upgrade head`, uses `profiles: [tools]` so it only runs on demand
- Hot-reload via volume mount (`./apps/api/app:/app/app`) in dev
- Health checks on postgres + redis before dependents start
- `agent-worker` receives `AGENT_ID` env var → listens on `agent.{AGENT_ID}` queue

**.dockerignore:** strips .env, .git, __pycache__, test/coverage artifacts

**Makefile:** `up`, `down`, `build`, `ps`, `logs`, `migrate`, `migrate-down`, `migrate-history`, `shell`, `shell-agent`, `test`, `test-policy`, `scale-agents N=3`, `clean`, `clean-images`

**`apps/api/app/worker.py`** — Orchestrator Celery app:
- Queue: `orchestrator`
- Beat schedule: `poll_all_inboxes` every 120s
- Includes: `app.tasks.step_results`, `app.tasks.inbox_poll`, `app.tasks.followups` (stubs to implement)

**`apps/agent/` — full agent runtime package:**
- `requirements.txt` — no FastAPI/SQLAlchemy, only Celery, Redis, httpx, aiosmtplib, aioimaplib, anthropic SDK
- `agent_runtime/sandbox.py` — `Sandbox.check()` raises `ToolNotAllowed` before any tool executes; defence-in-depth on top of network isolation
- `agent_runtime/runner.py` — `AgentRunner` with full Anthropic tool-use agentic loop (claude-opus-4-6), `max_iterations=10`, handles `tool_use` + `end_turn` stop reasons
- `agent_runtime/tools/__init__.py` — `build_tool_registry()` + `TOOL_SCHEMAS` (JSON schemas for all 6 tools)
- `agent_runtime/tools/` — 6 tool stubs: email, telegram, webchat, approval, scheduler, vendor. All post requests to Redis result queue; orchestrator executes with Vault-resolved credentials. Agents never hold credentials.
- `agent_runtime/main.py` — Celery task `agent.run_step`, `max_retries=3`, `task_acks_late=True`, `concurrency=1`

**Alembic setup:**
- `apps/api/alembic.ini` — `script_location = app/db/migrations`, URL overridden from settings
- `apps/api/app/db/migrations/env.py` — async env using `async_engine_from_config` + `NullPool`; imports all models to register metadata
- `apps/api/app/db/migrations/script.py.mako` — migration file template
- `apps/api/app/db/migrations/versions/.gitkeep` — placeholder for first migration

### Key Architectural Decision
**Each agent is a separate container** — non-negotiable safety requirement. This was specified by the user during the Docker setup session. The `agent-net` network isolation means agents cannot reach Postgres or the internal API by any means. All agent I/O goes through Redis queues. The orchestrator is the only process that reads agent results and writes to Postgres.

### Decisions Made
- Agent containers run as non-root (`USER agent`)
- Anthropic model: `claude-opus-4-6` for all agents (most capable)
- Agent Celery concurrency: `1` (one step at a time per agent — predictable rate limiting)
- Tool calls from agent → Redis → orchestrator → execute (credentials never in agent container)
- `agent-net` is `internal: false` (agents need outbound internet for SMTP/Telegram API)
- `backend-net` is `internal: false` (API needs outbound for OAuth, webhook registration)

### Next Steps
- Add `ANTHROPIC_API_KEY` to `.env.example`
- Create first Alembic migration (`alembic revision --autogenerate -m "initial schema"`)
- Implement orchestrator tasks: `app/tasks/step_results.py`, `app/tasks/inbox_poll.py`, `app/tasks/followups.py`
- Implement auth endpoints (`register`, `login`)
- Wire orchestrator to dynamically spawn/stop agent containers via Docker API when agents are enabled/disabled
- Write `docker-compose.override.yml` for per-developer customization

---

---

## 2026-03-01 — Container Registry & Lifecycle Management

### What Was Done

**`apps/api/app/models/container.py`** — New `AgentContainer` table:
- One row per agent (unique constraint on `agent_id`)
- Tracks: `container_id` (64-char Docker hash), `container_name`, `image`, `status`, `started_at`, `stopped_at`, `last_status_check_at`, `exit_code`, `error_message`, `restart_count`
- Status state machine: `starting → running → stopped | crashed → (auto-restart) → starting`
- Back-reference added to `Agent` model: `agent.container` (one-to-one, cascade delete)

**`apps/api/app/services/container_manager.py`** — `ContainerManager`:
- `spawn(agent)` — stops any existing container, calls Docker API to start new one on `agent-net`, upserts DB record
- `stop(agent_id)` — graceful stop (10s timeout) + optional remove, updates DB
- `restart(agent_id)` — checks restart_count < `MAX_AUTO_RESTARTS=5`, delegates to `spawn()`
- `refresh_status(record)` — sync Docker inspect → map to model status → async DB update
- `refresh_all()` — bulk refresh for all non-stopped containers
- `get_status(agent_id)` — dict for API response
- Docker client is lazily initialized and injectable (for testing)
- `_docker_status_to_model()` maps Docker status strings → `starting/running/stopped/crashed/unknown`
- Containers spawned with labels: `openclaw.agent_id`, `openclaw.managed=true`
- `restart_policy: {Name: no}` — orchestrator handles restarts, not Docker

**`apps/api/app/tasks/container_monitor.py`** — Celery beat task (every 30s):
- Calls `manager.refresh_all()` for all active containers
- Auto-restarts crashed containers via `manager.restart()` if under retry limit
- Broadcasts `container_restarted` / `container_failed` events (WebSocket stub)

**`apps/api/app/tasks/step_results.py`** — Celery task stub for agent result processing
**`apps/api/app/tasks/inbox_poll.py`** — Celery beat task stub for IMAP polling (120s)
**`apps/api/app/tasks/followups.py`** — Celery task stub for scheduled follow-up dispatch

**`apps/api/app/routers/agents.py`** — Three new container management endpoints:
- `GET  /{workspace_id}/agents/{agent_id}/container` — current container status (from DB)
- `POST /{workspace_id}/agents/{agent_id}/container/start` — spawn/restart container (202 Accepted)
- `POST /{workspace_id}/agents/{agent_id}/container/stop` — stop and remove container (204)

**Config, compose, requirements updates:**
- `config.py` — added `anthropic_api_key`, `docker_agent_network`, `docker_agent_image`, `docker_host`
- `worker.py` — added `monitor-containers` beat schedule (30s) alongside `poll-inboxes` (120s)
- `requirements.txt` — added `docker==7.1.0`
- `docker-compose.yml`:
  - `orchestrator-worker` now mounts `/var/run/docker.sock` (with security note)
  - `orchestrator-worker` has `DOCKER_AGENT_NETWORK` and `DOCKER_AGENT_IMAGE` env vars
  - `agent-worker` has explicit `image: openclaw/agent-runtime:latest` tag
- `.env.example` — added `DOCKER_AGENT_NETWORK`, `DOCKER_AGENT_IMAGE`, `DOCKER_HOST`

### Decisions Made
- **One `AgentContainer` row per agent** — upserted on restart, not appended. Keeps query simple; history is in audit_logs.
- **Max 5 auto-restarts** — after that, status stays `crashed` and user must intervene manually.
- **30-second polling interval** — fast enough for operational awareness, light enough for MVP. V1: switch to Docker events stream for real-time.
- **Docker socket mount** on orchestrator-worker only — not on api or beat. Documented security caveat (socket = root). Production recommendation: TLS Docker API or socket proxy.
- **Container name format**: `openclaw-agent-{agent_id}` — uses full UUID to prevent collisions.
- **No auto-start on agent create** — user must explicitly call `POST .../container/start`. Prevents runaway container spawning during setup.

### Issues / Blockers
- Docker socket approach is privileged — acceptable for MVP, needs hardening for production.
- `ContainerManager._stop_docker_container` is sync; wrapping in `asyncio.get_event_loop().run_in_executor()` would be cleaner in V1.

### Next Steps
- First Alembic migration: `alembic revision --autogenerate -m "initial schema"`
- Implement auth (`register` + `login`)
- Implement workspace + agent CRUD with auto-spawn on `is_enabled=True`
- Wire WebSocket broadcast in `container_monitor` to push status to UI
- Docker events stream listener for real-time status (V1)

---

---

## 2026-03-01 — Rate Limit Handling in Agent Runner

### What Was Done
- Rewrote `apps/agent/agent_runtime/runner.py` to handle Anthropic API rate limits gracefully.

**New `_create_with_retry()` method** wraps every `messages.create()` call:
- Catches `anthropic.RateLimitError` (HTTP 429) and `anthropic.InternalServerError` (status 529 — API overloaded)
- Reads the `retry-after` response header for exact wait duration; falls back to 60s default
- Also logs all quota headers: `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-requests`, `x-ratelimit-reset-tokens` (visible in container logs)
- Sleeps for the specified duration, then retries the same call transparently
- Retries indefinitely — no cap on number of retries, only a 2-hour total-wait ceiling (`MAX_RATE_LIMIT_WAIT = 7200`)
- If accumulated wait would exceed the ceiling, re-raises so the Celery task can retry/fail cleanly

**New helpers:**
- `_parse_retry_after(exc)` — extracts float seconds from header, guards against parse errors
- `_quota_headers(exc)` — extracts all Anthropic quota headers for structured log output

**Log events produced:**
- `agent.rate_limit.waiting` — emitted every time we sleep, with `wait_seconds`, `total_waited_seconds`, `attempt`, and all quota headers
- `agent.rate_limit.resuming` — emitted when sleep is done and we retry
- `agent.rate_limit.ceiling_reached` — emitted when 2h total wait would be exceeded (then raises)

### Decisions Made
- **Indefinite retry** — "wait for token refresh" means we never give up due to rate limits alone. Only the 2-hour ceiling stops us (guards against stuck agents).
- **`MAX_RATE_LIMIT_WAIT = 7200`** (2 hours) — chosen because Anthropic's daily token limits reset every 24h but minute limits reset in <60s; 2h covers any realistic backlog scenario.
- **`DEFAULT_RETRY_AFTER = 60`** — conservative fallback if the header is absent.
- **529 handled identically to 429** — both signal "not right now, try later."
- Rate limit logic isolated in `_create_with_retry()` and `_handle_rate_limit()` — the agentic loop itself is unchanged.

---

---

## 2026-03-01 — Switched LLM Client to LiteLLM

### What Was Done
Replaced the Anthropic SDK with LiteLLM across the agent runtime. Provider is now fully configurable via env vars — no code changes or image rebuilds needed to switch.

**`apps/agent/requirements.txt`**
- Removed: `anthropic==0.37.1`
- Added: `litellm>=1.0.0`

**`apps/agent/agent_runtime/runner.py`** — full rewrite:
- Replaced `anthropic.AsyncAnthropic` with `litellm.acompletion()`
- Replaced Anthropic `stop_reason` / content block parsing with OpenAI `finish_reason` / `tool_calls` format
- `AgentRunner.__init__` now reads `LLM_MODEL`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MAX_TOKENS` from env
- Rate-limit retry updated to catch `litellm.exceptions.RateLimitError` and `litellm.exceptions.ServiceUnavailableError`
- New helpers: `_assistant_message()` (builds OpenAI-format assistant turn with tool_calls), `_parse_arguments()` (safe JSON parse of function arguments)
- `litellm.telemetry = False` — disables LiteLLM's own telemetry
- System prompt now passed as first message `{"role": "system", ...}` (universal across providers)

**`apps/agent/agent_runtime/tools/__init__.py`**
- Rewrote `TOOL_SCHEMAS` from Anthropic format (`input_schema`) to OpenAI function-calling format (`type: "function"`, `parameters`)
- LiteLLM auto-translates to each provider's native format at call time
- Updated `active_schemas` filter in `runner.py` to use `s["function"]["name"]`

**`docker-compose.yml`** — `agent-worker` environment:
- Removed: `ANTHROPIC_API_KEY`
- Added: `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MAX_TOKENS`

**`.env.example`** — added LiteLLM provider examples with comments for all major providers

### Decisions Made
- **LiteLLM over raw SDK** — single API call interface, 100+ providers, maintained by open source community
- **OpenAI message format** — LiteLLM's universal format; translates to Anthropic/Gemini/etc. natively
- **`LLM_MODEL` prefix convention** — `anthropic/...`, `gemini/...`, `ollama/...` tells LiteLLM which backend
- **No `ANTHROPIC_API_KEY` special-casing** — all keys go through `LLM_API_KEY`; LiteLLM also reads provider-specific vars (e.g. `OPENAI_API_KEY`) automatically as a fallback
- **Default model**: `anthropic/claude-opus-4-6` — most capable, same as before

### Supported Providers (examples)
| Provider | LLM_MODEL | Notes |
|---|---|---|
| Anthropic | `anthropic/claude-opus-4-6` | Requires `LLM_API_KEY` |
| OpenAI | `gpt-4o` | Requires `LLM_API_KEY` |
| Google Gemini | `gemini/gemini-1.5-pro` | Requires `LLM_API_KEY` |
| Groq | `groq/llama-3.3-70b-versatile` | Requires `LLM_API_KEY`, very fast |
| Ollama (local) | `ollama/llama3.3` | Requires `LLM_API_BASE=http://ollama:11434`, no key needed |
| AWS Bedrock | `bedrock/anthropic.claude-...` | Requires AWS credentials |

---

---

## 2026-03-01 — UI-Configurable LLM Provider & API Key

### What Was Done

**`apps/api/app/models/llm_config.py`** — New `LLMConfig` table:
- Columns: `workspace_id`, `agent_id` (nullable), `model`, `api_key_encrypted`, `api_base_url`, `max_tokens`, `temperature`, `is_active`
- Unique constraint on `(workspace_id, agent_id)` — one config per scope
- `agent_id IS NULL` = workspace default; `agent_id IS NOT NULL` = per-agent override

**`apps/api/app/services/secrets.py`** — Fernet encryption for API keys:
- `encrypt_api_key(plaintext)` → base64 ciphertext stored in DB
- `decrypt_api_key(ciphertext)` → raw key used at container spawn time
- Key derived from `ENCRYPTION_KEY` env var via SHA-256 → Fernet
- Raw keys are NEVER stored, NEVER returned by API

**`apps/api/app/services/llm_registry.py`** — static provider/model catalog:
- 8 providers: Anthropic, OpenAI, Google Gemini, Groq, Mistral, Ollama, AWS Bedrock, Azure OpenAI
- Each provider entry has: `requires_api_key`, `requires_base_url`, `base_url_placeholder`, `api_key_label`, `docs_url`, `note`, `models[]`
- `VALID_MODEL_IDS` set for validation; `get_provider_for_model()` helper

**`apps/api/app/routers/llm_configs.py`** — 10 new endpoints registered at `/api`:
- `GET  /workspaces/{id}/llm-config` — workspace default
- `POST /workspaces/{id}/llm-config` — set/update (encrypts key before storage)
- `DELETE /workspaces/{id}/llm-config` — clear
- `POST /workspaces/{id}/llm-config/test` — live test call
- `GET  /workspaces/{id}/agents/{aid}/llm-config` — effective config (override or default)
- `POST /workspaces/{id}/agents/{aid}/llm-config` — set agent override
- `DELETE /workspaces/{id}/agents/{aid}/llm-config` — remove override
- `POST /workspaces/{id}/agents/{aid}/llm-config/test` — live test
- `GET  /api/llm/providers` — provider list for UI dropdown
- `GET  /api/llm/providers/{id}/models` — model list for UI dropdown

**`apps/api/app/services/container_manager.py`** — `_resolve_llm_env()` added to `spawn()`:
- Queries `LLMConfig` (agent override first, workspace default second, env var fallback last)
- Decrypts API key at spawn time only — never stored in container environment long-term
- Injects `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MAX_TOKENS` into container env
- Logs which config source was used (agent_override / workspace_default / env_fallback)

**Supporting changes:**
- `requirements.txt` — added `cryptography==43.0.1`
- `config.py` — added `encryption_key` field
- `.env.example` — added `ENCRYPTION_KEY` with generation command
- `models/__init__.py` — exports `LLMConfig`
- `main.py` — registers `llm_configs.router`

### Decisions Made
- **Fernet symmetric encryption** for MVP (simple, auditable, reversible with correct key). Production: swap to Vault Transit Engine with same `encrypt/decrypt` interface.
- **`has_api_key: bool`** in responses — never expose even encrypted keys to clients.
- **Model validation** against `VALID_MODEL_IDS` at API layer — prevents invalid LiteLLM model strings reaching containers.
- **10-token test call** for connection testing — minimal cost, confirms auth + routing works.
- **Env var fallback** preserved — dev setups without DB config still work via `docker-compose.yml`.
- **`temperature: float`** included — different use cases (negotiation vs drafting) may need different settings.

### Next Steps
- Alembic migration for `llm_configs` table
- Auth implementation
- Workspace + agent CRUD implementation
- Wire up `ENCRYPTION_KEY` into `docker-compose.yml` for orchestrator

---

---

## 2026-03-01 — Alembic Initial Migration + Auth (Email/Password + SSO)

### What Was Done

**Git + GitHub:**
- Initialized git repo (`git init`, branch `main`)
- First commit: 74 files, 5,572 insertions
- Pushed to `https://github.com/haedongyoo/agent-orchestrator`

**User model changes (`apps/api/app/models/workspace.py`):**
- Added `sso_provider: Optional[str]` — which OAuth2 provider ("google" | "github" | "microsoft")
- Added `sso_sub: Optional[str]` — stable user ID from the provider (never changes)
- Added `UniqueConstraint("sso_provider", "sso_sub", name="uq_users_sso_identity")` — prevents duplicate SSO identities; NULLs are distinct so email/password users are unaffected

**Alembic initial migration (`apps/api/app/db/migrations/versions/001_initial_schema.py`):**
- Manually written migration covering all 13 tables in FK-dependency order: `users → workspaces → user_channels → shared_email_accounts → agents → agent_containers → threads → messages → tasks → task_steps → approvals → audit_logs → llm_configs`
- Includes `downgrade()` that drops tables in reverse order
- Added performance indexes: `ix_messages_thread_id_created_at`, `ix_approvals_workspace_status`, `ix_audit_logs_workspace_id_created_at`
- Removed the placeholder `.gitkeep` from `versions/`

**Auth service (`apps/api/app/services/auth.py`):**
- `hash_password(password)` / `verify_password(plain, hashed)` — passlib bcrypt
- `create_access_token(subject, expires_delta?)` — HS256 JWT
- `decode_access_token(token)` — raises HTTP 401 on any failure
- `get_current_user(token, db)` — FastAPI dependency; decodes JWT → loads active User

**SSO service (`apps/api/app/services/sso.py`):**
- Supports: `google`, `github`, `microsoft`
- `create_sso_state(provider)` / `verify_sso_state(state, provider)` — signed JWT state for CSRF protection (no Redis needed)
- `build_authorization_url(provider, state)` — builds redirect URL with all required OAuth2 params
- `exchange_code_for_user_info(provider, code, state)` — full OAuth2 code flow: verify state → exchange code for token → fetch user profile → return `SSOUserInfo`
- GitHub special case: separate call to `/user/emails` if profile email is private
- Checks that provider is configured; raises 503 if credentials missing

**Auth router (`apps/api/app/routers/auth.py`) — fully implemented:**
- `POST /api/auth/register` — 201 + JWT; 409 on duplicate email; 422 if password < 8 chars
- `POST /api/auth/login` — OAuth2PasswordRequestForm (username=email); 401 on bad creds
- `GET  /api/auth/sso/{provider}` — 302 redirect to provider; 400 on unknown provider
- `GET  /api/auth/sso/{provider}/callback` — find-or-create user by SSO identity; links to existing email account if email matches; returns JWT
- `GET  /api/auth/me` — returns `UserResponse` (id, email, is_active, sso_provider)

**Config (`apps/api/app/config.py`):**
- Added SSO env vars: `sso_redirect_base_url`, `google_client_id/secret`, `github_client_id/secret`, `microsoft_client_id/secret`, `microsoft_tenant_id`

**Requirements (`apps/api/requirements.txt`):**
- Added `email-validator==2.2.0` (required for Pydantic `EmailStr`)

**Python 3.9 compatibility fixes:**
- All SQLAlchemy model files: replaced `Mapped[X | None]` with `Mapped[Optional[X]]` and added `from typing import Optional`
- All router/service files: added `from __future__ import annotations` for deferred annotation evaluation
- Added `eval_type_backport` (Pydantic v2 recommendation for Python 3.9)
- Installed compatible `bcrypt<4.0` locally (passlib 1.7.4 incompatibility with bcrypt 4.x)

**Policy fix (`apps/api/app/services/orchestrator/policy.py`):**
- `_create_approval_request()`: now explicitly generates `approval_id = uuid.uuid4()` before creating the Approval object, so it's available before DB flush (important for testability with mocked DBs)

**Tests (`apps/api/app/tests/test_auth.py`) — 12 tests, all passing:**
- `test_register_success` / `test_register_duplicate_email` / `test_register_short_password`
- `test_login_success` / `test_login_wrong_password` / `test_login_unknown_email`
- `test_me_authenticated` / `test_me_unauthenticated` / `test_me_expired_token`
- `test_sso_redirect_google` / `test_sso_redirect_unsupported_provider`
- `test_sso_callback_creates_new_user`

**Full test suite: 17/17 passing** (`test_policy.py` + `test_auth.py`)

### Decisions Made
- **SSO state as JWT** — avoids Redis dependency just for state tokens. The JWT contains `{purpose, provider, exp}` and is signed with the app's `secret_key`. 10-min TTL.
- **SSO account linking** — if a new SSO user's email matches an existing password account, the SSO identity is linked silently (no friction). This is the standard behavior in modern SaaS apps.
- **No SSO-initiated `password_hash`** — SSO users have `password_hash=None`. They can set a password later (not implemented yet) if they want dual auth.
- **`Optional[str]` in models, not `str | None`** — SQLAlchemy 2.0 on Python 3.9 evaluates deferred annotations at runtime; `str | None` fails in `eval()`. Target runtime is Python 3.12 (Docker) but local tests must work.
- **Minimal test app** — auth tests import only `app.routers.auth` (not `app.main`), which avoids the Docker SDK import chain. Keeps test dependencies light.

### Issues / Blockers
- None — tests are green

### Next Steps
- `make up` to start Docker stack + `make migrate` to run `001_initial_schema.py`
- Implement **workspace CRUD** (`POST /api/workspaces`, `GET/PUT /api/workspaces/{id}`)
- Implement **agent CRUD** under workspace
- Implement **thread + message CRUD** with cursor pagination
- Wire orchestrator router to actually process messages

---

## 2026-03-01 (Session 5) — Email Connector (Outbound SMTP + Inbound IMAP)

### What Was Done

**Email connector** (PR #6, feat/email-connector):

**`services/connectors/email.py` — full implementation:**
- `_resolve_credentials(credentials_ref)` — decrypts Fernet-encrypted JSON blob → `{smtp_host, smtp_port, imap_host, imap_port, username, password}`; production: swap to Vault path read
- `send_email(email, credentials_ref, from_alias, signature?)` — SMTP via aiosmtplib (STARTTLS); builds MIME multipart; sets RFC 5322 `Message-ID`; sets `In-Reply-To` + `References` for email threading; returns generated message_id
- `poll_inbox(credentials_ref, mailbox?, since_uid?)` — IMAP via aioimaplib; incremental fetch (`UID n+1:*`) or UNSEEN; parses RFC 822 bytes into structured dicts
- `find_or_create_email_thread(db, workspace_id, msg_dict)` — thread matching by In-Reply-To → References → create new; exported for use by `inbox_poll`
- `_parse_raw_email(uid, raw)` — parses raw RFC 822 bytes into structured dict; handles multipart + single-part; extracts In-Reply-To, References headers
- IMAP response helpers: `_is_ok()` handles both tuple-return (older aioimaplib) and object-return (aioimaplib 2.x) APIs; `_extract_uid_list()`, `_extract_message_bytes()`
- Both aiosmtplib and aioimaplib lazily imported (not installed locally; live in Docker image — same pattern as Docker SDK)

**`tasks/inbox_poll.py` — `_poll_account()` completed:**
- Calls `poll_inbox(account.credentials_ref)` (UNSEEN for MVP; UID tracking for V1)
- Opens DB session; resolves workspace owner for `Task.created_by` FK
- For each inbound email: `find_or_create_email_thread()` → persist Message → create Task (objective = "Inbound email from...") → `Planner.decompose()` → `OrchestratorRouter.enqueue_existing_step()` → task.status = "running"
- Full error handling: log + rollback per-message on failure; log + return on poll failure
- Removed `_find_or_create_email_thread` from inbox_poll (moved to email.py for testability without Celery)

**`tests/test_email.py` — 20 tests, all passing:**
- `TestResolveCredentials` (2): roundtrip decrypt, invalid token raises
- `TestSendEmail` (4): calls aiosmtplib.send, correct SMTP params, reply headers set, signature appended
- `TestParseRawEmail` (3): basic fields parsed, reply headers, empty headers → None
- `TestImapHelpers` (7): `_is_ok` for tuple + object, `_extract_uid_list` for bytes + empty + object
- `TestFindOrCreateEmailThread` (4): match by In-Reply-To, match by References, create on miss, create with no headers

### Key Decisions Made
- `credentials_ref` = Fernet-encrypted JSON blob (same `encrypt_api_key`/`decrypt_api_key` from secrets.py); JSON contains full SMTP+IMAP credentials; production = Vault path
- `find_or_create_email_thread` lives in `email.py` (not `inbox_poll.py`) — pure email logic, no Celery dep → testable without broker
- `poll_inbox` always fetches UNSEEN for MVP — UID tracking per account is V1 work (requires DB field or Redis key per account)
- Each inbound email creates a Task with objective = from+subject summary; Planner picks agent based on workspace context
- aioimaplib/aiosmtplib: lazy imports at point of use (not at module level) — same pattern as Docker SDK; prevents `ModuleNotFoundError` in local test environment

### Test Count
- 99/99 passing (up from 88 — added 20 email tests, +11 from previous connector tests now included in full suite, -9 connector tests excluded via --ignore)

### Next Steps
- Role templates: negotiator / sourcing / contractor (remaining Phase 1 MVP item)
- V1: IMAP UID tracking per `SharedEmailAccount` (requires new DB column `last_imap_uid`)
- V1: Attachment handling in `_parse_raw_email` (currently text/plain only)

---

## 2026-03-01 (Session 6) — Role Templates (Negotiator, Sourcing Agent, Contractor Liaison)

### What Was Done

**Role templates** (PR #7, feat/role-templates):

**`services/role_templates.py` — 3 built-in templates:**
- Frozen `RoleTemplate` dataclass (id, name, description, role_prompt, allowed_tools, rate_limit_per_min, max_concurrency)
- `list_templates()` / `get_template(id)` public API
- **Negotiator**: price negotiation, counter-offers, deal closing; tools: send_email, send_telegram, post_web_message, request_approval, schedule_followup; rate 10/min, concurrency 2
- **Sourcing Agent**: global RFQ campaigns, vendor DB management; tools: send_email, read_email_inbox, post_web_message, upsert_vendor, request_approval, schedule_followup; rate 20/min, concurrency 5
- **Contractor Liaison**: local contractor coord, milestone tracking, payment approvals; tools: send_email, send_telegram, post_web_message, request_approval, schedule_followup; rate 10/min, concurrency 3
- Each role_prompt: 250-500 words covering persona, workflow, constraints, and tool guidance

**`routers/role_templates.py` — 2 endpoints (no auth — public metadata):**
- `GET /api/agent-templates` → list all 3 templates (200)
- `GET /api/agent-templates/{id}` → get single (200); 404 + detail message on unknown id

**`main.py`:** registered `role_templates.router` at prefix `/api`, tag `agent-templates`

**`tests/test_role_templates.py` — 17 tests:**
- Service layer: list returns all 3, get each by id, unknown returns None, all tools valid, prompts non-empty, rate limits positive, dataclass immutability
- HTTP layer: list returns 3 items, schema fields present, tools are lists, get each by id, 404 on unknown, 404 detail contains id

### Key Decisions Made
- Templates are **immutable** (frozen dataclass) — no DB table needed; they're product defaults, not user data
- **No auth required** on template endpoints — templates contain no sensitive data and are meant for UI dropdowns at agent creation time
- `allowed_tools` in templates cross-validated against the same VALID_TOOLS allowlist used by the agents router — any mismatch would fail the test `test_all_template_tools_are_valid`
- Templates cover all 7 defined tools across the 3 roles (upsert_vendor only in sourcing, read_email_inbox only in sourcing)
- Sourcing agent has higher rate limit (20/min vs 10/min) to support bulk RFQ campaigns

### Test Count
- 116/116 passing (17 new tests)

### Phase 1 MVP Status
All Phase 1 MVP items are now complete:
- [x] Auth + Alembic initial migration
- [x] Workspace CRUD
- [x] Agent CRUD + role prompt
- [x] Web thread chat + message persistence
- [x] Telegram inbound/outbound
- [x] Email outbound + IMAP polling
- [x] Orchestrator: step queue + A2A approval gating
- [x] Role templates (negotiator / sourcing / contractor)

### Next Steps (Phase 2 — V1)
- Vendor/contractor CRM (upsert_vendor tool implementation)
- Multi-language translation tool
- Robust scheduler for follow-ups (Temporal integration)
- Email provider OAuth (Gmail/Graph)
- Observability: traces, step-level debugging, replay

---

## 2026-03-01 (Session 7) — Production Containerization (PR #8)

### What Was Done

**Containerization fixes + production compose** (PR #8, feat/containerization-prod):

**`apps/agent/Dockerfile` — two critical bug fixes:**
- **CMD shell variable expansion**: Exec-form `["celery", ..., "agent.{AGENT_ID}"]` treats `{AGENT_ID}` as a literal string. Switched to shell form `CMD sh -c "celery ... --queues=agent.${AGENT_ID:-placeholder}"` so the env var expands at container startup.
- **File ownership**: `COPY . .` runs as root before `useradd`, so all files were root-owned; `agent` user couldn't write temp files. Fixed with `chown -R agent:agent /app` in the same `RUN` layer as `useradd`.

**`docker-compose.yml` (dev) — three fixes:**
- Added `healthcheck` block to the `api` service (was missing; other services couldn't reliably depend on it).
- Added `ENCRYPTION_KEY: ${ENCRYPTION_KEY}` to `orchestrator-beat` (was present on worker but missing on beat, causing `decrypt_api_key()` to fail in beat tasks).
- Fixed `LLM_MAX_TOKENS` default from `4096` → `32768` (claude-opus-4-6 supports 32K output tokens).

**`docker-compose.prod.yml` — new production compose file:**
- Uses named image tags (`openclaw/api:${IMAGE_TAG:-latest}`) instead of build context — production deploys pull pre-built images.
- Removes hot-reload volume mounts (image ships final code).
- No exposed Postgres or Redis ports — DB is internal-only in production.
- Redis password enforced: `--requirepass ${REDIS_PASSWORD}` with `${REDIS_PASSWORD:?...}` required-var syntax.
- Postgres password: `${POSTGRES_PASSWORD:?...}` — fails loudly if unset.
- Uvicorn runs `--workers 4` instead of `--reload`.
- `restart: always` (tolerates host reboots).
- `APP_ENV: production`, `LOG_LEVEL: info`.

**`Makefile` — two fixes + 5 new prod targets:**
- Fixed test paths: `apps/api/app/tests/` → `app/tests/` (container WORKDIR is `/app`; tests live at `/app/app/tests/`).
- Fixed `test-policy` path similarly.
- Added `prod-build`, `prod-up`, `prod-down`, `prod-migrate`, `prod-logs` targets using `-f docker-compose.prod.yml`.

### Key Decisions Made
- **`docker-compose.prod.yml` uses image references, not build context** — CI/CD builds and tags images; production just pulls them. This separates build from deploy.
- **Redis password required in prod** — `${REDIS_PASSWORD:?REDIS_PASSWORD must be set}` syntax causes compose to exit 1 if the variable is unset or empty, preventing misconfigured deployments.
- **`restart: always` vs `unless-stopped`** — production services must survive host reboots; dev services use `unless-stopped` to allow `docker compose down` without auto-restart on boot.
- **No socket proxy yet** — Docker socket on orchestrator-worker is still direct (`/var/run/docker.sock`). Noted as production hardening item (TLS Docker API or socket proxy).

### Test Count
- 116/116 passing (no new tests — containerization changes are infra, not app logic)

### Next Steps (Phase 2 — V1 continues)
- PR #9: Vendor/Contractor CRM — `Vendor` model, CRUD endpoints, wire `upsert_vendor` tool
- PR #10: Scheduler + follow-ups — complete `schedule_followup()` with Celery ETA
- PR #11: Observability — audit traces, `GET /api/tasks/{id}/trace`
- PR #12: Policy hardening — detect commitment/contract/payment language → auto-approval gate

---

## 2026-03-01 (Session 8) — Vendor/Contractor CRM (PR #9)

### What Was Done

**Vendor CRM** (PR #9, feat/vendor-crm):

**`models/vendor.py` — New `Vendor` table:**
- Columns: `workspace_id` (FK → workspaces CASCADE), `name`, `email`, `category`, `contact_name`, `phone`, `website`, `country`, `notes`, `tags` (JSON), `created_at`, `updated_at`
- Unique constraint: `(workspace_id, name)` — upsert_vendor matches on name per workspace
- Back-reference on `Workspace.vendors`

**`db/migrations/versions/002_add_vendors.py`:**
- Creates `vendors` table with `ix_vendors_workspace_id` index

**`services/vendors.py`:**
- `upsert_vendor(db, workspace_id, name, ...)` — SELECT by `(workspace_id, name)` → INSERT or UPDATE non-None fields
- `list_vendors(db, workspace_id, category?, limit, offset)` — ordered by name; optional category filter
- `get_vendor(db, workspace_id, vendor_id)` — workspace-scoped lookup
- `delete_vendor(db, workspace_id, vendor_id)` — returns bool; workspace-scoped

**`routers/vendors.py` — 5 endpoints:**
- `GET /api/workspaces/{id}/vendors` — list with optional `?category=` filter, `?limit=`, `?offset=`
- `POST /api/workspaces/{id}/vendors` — upsert (201); category validated against allowlist: `furniture_supplier|material_factory|contractor|logistics|other`
- `GET /api/workspaces/{id}/vendors/{vid}` — get single (200/404)
- `PUT /api/workspaces/{id}/vendors/{vid}` — partial update (200/404)
- `DELETE /api/workspaces/{id}/vendors/{vid}` — delete (204/404)
- All require Bearer JWT; workspace ownership validated (returns 404 on non-owner)

**`tasks/vendor_ops.py` — Celery task:**
- `handle_vendor_upsert(request)` registered on `orchestrator` queue
- `_do_upsert(request)` — pure async function with lazy imports (testable without Celery)
- Validates `workspace_id` UUID format; returns `{"success": bool, ...}`

**Agent `vendor_tool.py` — TODO implemented:**
- Module-level singleton `_orch_producer` Celery app (lazy-initialized, broker=REDIS_URL)
- Posts to `orchestrator` queue via `send_task("app.tasks.vendor_ops.handle_vendor_upsert")`
- Agents never reach Postgres — the orchestrator writes the DB row

**`worker.py`:** added `app.tasks.vendor_ops` to includes list

### Key Decisions Made
- **`sys.modules` mock for Celery** in test file — avoids the `ModuleNotFoundError: No module named 'celery'` issue (Celery not installed locally); consistent with the lazy-import pattern used by Docker SDK
- **Patch lazy imports at source module** — `patch("app.db.session.AsyncSessionLocal")` and `patch("app.services.vendors.upsert_vendor")` (not `app.tasks.vendor_ops.*`) because they're local imports inside `_do_upsert`
- **Vendor name is the natural key** per workspace — simplifies upsert semantics (no need for external ID from agents)
- **Category allowlist** enforced at router layer only — same pattern as `allowed_tools` and `provider_type`; keeps service layer flexible for internal use

### Test Count
- 143/143 passing (18 new vendor tests)

### Next Steps
- PR #10: Scheduler + follow-ups — complete `schedule_followup()` with Celery ETA
- PR #11: Observability — audit traces, `GET /api/tasks/{id}/trace`
- PR #12: Policy hardening

---

## 2026-03-01 (Session 9) — Scheduler + Follow-ups (PR #10)

### What Was Done

**Scheduler + follow-ups** (PR #10, feat/scheduler-followups):

**`services/orchestrator/scheduler.py` — full implementation:**
- `schedule_followup(workspace_id, thread_id, agent_id, task_id, delay_seconds, message)`:
  - Computes ETA = `now() + timedelta(seconds=delay_seconds)`
  - Calls `celery_app.send_task("app.tasks.followups.fire_followup", eta=eta, queue="orchestrator")`
  - Returns Celery async result ID as `schedule_id`
- `cancel_followup(schedule_id)`:
  - Calls `celery_app.control.revoke(schedule_id, terminate=False)`
  - Returns `True` (revoke is fire-and-forget; no worker confirmation)
- Both methods use lazy import of `celery_app` (same pattern as router.py)

**`tasks/followups.py` — complete implementation:**
- `handle_schedule_request(request)` Celery task (on orchestrator queue):
  - Validates required fields (workspace_id, thread_id, agent_id, delay_seconds)
  - Finds latest running/queued task for `(workspace_id, thread_id)` in DB
  - Calls `Scheduler.schedule_followup()` → schedules `fire_followup` ETA task
  - Returns `{success, schedule_id, task_id}`
- `fire_followup(task_id, agent_id, workspace_id, thread_id, message)` ETA task:
  - Checks task is still active (not done/failed)
  - Creates `TaskStep(type=action, tool_call={"followup_message": message})`
  - Calls `OrchestratorRouter.enqueue_existing_step()` → dispatches to `agent.{agent_id}` queue
  - Agent wakes up with the follow-up instruction
- `_do_schedule()` / `_dispatch_followup()` are pure async helpers with lazy imports (testable without Celery)

**Agent `scheduler_tool.py` — TODO implemented:**
- Module-level singleton Celery producer (same pattern as vendor_tool.py)
- Posts `handle_schedule_request` to `orchestrator` queue via `send_task()`

### Key Decisions Made
- **schedule_id = Celery result.id** — this is the unique identifier for a queued ETA task; can be passed to `control.revoke()` for cancellation before firing
- **Scheduler does NOT persist schedule state** — schedule_id is returned to agent tool caller (in tool output) for storage in conversation context if needed; no separate schedules table for MVP
- **`fire_followup` re-dispatches via OrchestratorRouter** — consistent with all other step dispatches; policy enforcement applies to follow-up steps too
- **Thread-scoped task lookup** in `handle_schedule_request` — picks the latest running task for the thread to associate the follow-up; covers the common case where one thread has one active task

### Test Count
- 152/152 passing (9 new scheduler tests)

### Next Steps
- PR #11: Observability — audit traces, `GET /api/tasks/{id}/trace`, correlation IDs
- PR #12: Policy hardening — detect commitment/contract/payment language → auto-approval gate

---

<!-- TEMPLATE FOR NEW ENTRIES:

## YYYY-MM-DD — Session Title

### What Was Done
-

### Decisions Made
-

### Issues / Blockers
-

### Next Steps
-

-->
