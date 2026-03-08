# OpenClaw Agent Orchestrator — CLAUDE.md

This file is the authoritative project reference for Claude Code. Read this before making any changes.
**Source of truth**: `agent-orchestrator.md`. Keep this file in sync with the plan.

---

## Project Goal

Build **OpenClaw Agents** — a service that runs multiple AI agents as "always-on employees" for 24/7 negotiation, sourcing, and workflow automation (furniture suppliers, material factories, local contractors, multi-language). Nag hb

Users configure agents with roles, connect channels (Telegram, Email, Web), and interact through a unified orchestration UI.

---

## Core Constraints (Non-Negotiable)

1. **Agent-to-agent communication is OFF by default.** Any A2A message requires an explicit approval workflow (scoped by agents, thread, duration, content type).
2. **All message routing goes through the orchestrator** — agents cannot call each other directly.
3. **No credentials in plaintext DB** — use Vault/KMS; DB stores only `credentials_ref`.
4. **Every outbound action is audited** — which agent, which approval, which task.
5. **Agents are sandboxed** — only allowed tools, no direct network access to internal services.

---

## Architecture Overview

```
User
 ├── Web UI (WebSocket/SSE)
 ├── Telegram (per-agent bot tokens)
 └── Email (shared inbox: IMAP/Gmail/Graph)
        │
        ▼
   [ Connectors Layer ]
        │
        ▼
   [ Orchestrator ]  ←→  [ Policy Engine ]
     - router.py            - A2A enforcement
     - planner.py           - approval checks
     - scheduler.py         - domain allow/deny lists
        │
        │ Redis queues only (agent.{agent_id})
        ▼
   [ Agent Runtime Containers ] ← ONE CONTAINER PER AGENT (non-negotiable)
     - sandboxed tool layer        Only on agent-net
     - role prompt + context       Cannot reach Postgres or API directly
     - non-root user               All I/O via Redis result queues
        │
        ▼
   [ Redis ]  ←→  [ Orchestrator reads results → Postgres ]
```

### Network Segmentation (Docker)

```
backend-net:  api, orchestrator-worker, orchestrator-beat, postgres, redis
agent-net:    agent-worker-* (per agent), redis

Agents are on agent-net ONLY.
They cannot resolve postgres or api hostnames.
They communicate with the orchestrator via Redis queues exclusively.
```

---

## Tech Stack

| Layer | MVP | Production |
|---|---|---|
| API | FastAPI (Python) | FastAPI |
| DB | Postgres | Postgres |
| Queue | Redis + Celery/RQ | Temporal |
| Realtime | WebSocket | WebSocket/SSE |
| Telegram | Webhook bot | Webhook bot |
| Email | IMAP/SMTP | OAuth (Gmail/Graph) |
| Secrets | Env vars | Vault/KMS |
| Agent runtime | OpenClaw via LiteLLM (isolated containers) | OpenClaw via LiteLLM |
| LLM | LiteLLM — switch provider via `LLM_MODEL` env var | LiteLLM |

---

## Repo Layout

```
repo/
  apps/
    api/                          # API + Orchestrator (backend-net)
      Dockerfile
      requirements.txt
      alembic.ini
      app/
        main.py
        config.py
        worker.py                 # Celery orchestrator worker
        routers/
          auth.py
          workspaces.py
          agents.py
          threads.py
          tasks.py
          approvals.py
        services/
          orchestrator/
            router.py             # routes messages, enforces A2A policy
            planner.py            # task → steps decomposition
            policy.py             # approval checks, domain lists, rate limits
            scheduler.py          # follow-ups, retries, periodic triggers
          connectors/
            telegram.py
            email.py
            webchat.py
        models/
          workspace.py
          agent.py
          thread.py
          message.py
          task.py
          approval.py
          audit.py
        db/
          session.py
          migrations/
            env.py
            script.py.mako
            versions/
        tests/
          test_policy.py
          test_orchestrator.py
          test_connectors.py

    agent/                        # Agent Runtime (agent-net ONLY)
      Dockerfile                  # Runs as non-root user
      requirements.txt            # No FastAPI/SQLAlchemy — queue + Anthropic SDK only
      agent_runtime/
        main.py                   # Celery worker, queue: agent.{agent_id}
        runner.py                 # OpenClaw agentic loop (Anthropic tool-use)
        sandbox.py                # Enforces allowed_tools at runtime
        tools/
          __init__.py             # Tool registry builder + JSON schemas
          email_tool.py
          telegram_tool.py
          webchat_tool.py
          approval_tool.py
          scheduler_tool.py
          vendor_tool.py

  docker-compose.yml              # Services: api, orchestrator-worker, orchestrator-beat,
  .dockerignore                   #           agent-worker, postgres, redis, migrate
  Makefile                        # make up/down/migrate/test/scale-agents
  .env.example
  .gitignore
  CLAUDE.md
  DEV_LOG.md
  agent-orchestrator.md           # Source of truth plan
```

---

## Data Model Summary

### Identity / Auth
- `users`: id, email, password_hash/SSO, created_at
- `workspaces`: id, user_id, name, timezone, language_pref

### Channel Config
- `user_channels`: workspace_id, user_telegram_chat_id, web_chat_enabled
- `shared_email_accounts`: workspace_id, provider_type, credentials_ref, from_alias, signature_template
- `agents`: id, workspace_id, name, role_prompt, allowed_tools (json), telegram_bot_token_ref, is_enabled, rate_limit_per_min, max_concurrency

### Conversations
- `threads`: id, workspace_id, title, status, linked_telegram_chat_id, linked_email_thread_id
- `messages`: id, thread_id, sender_type, sender_id, channel, content, metadata (json), created_at

### Tasks / Steps
- `tasks`: id, workspace_id, thread_id, objective, status (queued/running/blocked/needs_approval/done/failed), created_by, created_at
- `task_steps`: id, task_id, agent_id, step_type, tool_call (json), result (json), status, created_at

### Approvals + Audit
- `approvals`: id, workspace_id, thread_id, task_id, approval_type, requested_by, approved_by, scope (json), status (pending/approved/rejected), created_at, decided_at
- `audit_logs`: id, workspace_id, actor_type, actor_id, action, target_type, target_id, detail (json), created_at

---

## API Endpoints

### Workspace & Settings
- `POST /api/workspaces`
- `GET/PUT /api/workspaces/{id}`
- `POST /api/workspaces/{id}/shared-email`
- `POST /api/workspaces/{id}/agents`
- `GET /api/workspaces/{id}/agents`
- `PUT/DELETE /api/workspaces/{id}/agents/{agentId}`

### Threads & Messages
- `POST /api/workspaces/{id}/threads`
- `GET /api/threads/{threadId}`
- `POST /api/threads/{threadId}/messages`
- `GET /api/threads/{threadId}/messages?cursor=...`

### Tasks
- `POST /api/threads/{threadId}/tasks`
- `GET /api/tasks/{taskId}`
- `POST /api/tasks/{taskId}/cancel`

### Approvals
- `GET /api/workspaces/{id}/approvals?status=pending`
- `POST /api/approvals/{approvalId}/approve`
- `POST /api/approvals/{approvalId}/reject`

### Realtime
- `WS /ws/threads/{threadId}` — events: `new_message`, `task_status`, `approval_requested`, `approval_decided`

---

## Agent Tool Contracts

```python
request_approval(type, scope, reason) -> approval_id
send_email(to, subject, body, thread_id, attachments?) -> message_id
read_email_inbox(thread_id | mailbox_ref) -> messages
send_telegram(chat_id, text, thread_id) -> message_id
post_web_message(thread_id, text) -> message_id
upsert_vendor(profile) -> vendor_id
schedule_followup(task_id, when, payload) -> schedule_id
```

---

## Implementation Phases

### Phase 1 — MVP
- [x] **Auth — email/password + SSO (Google, GitHub, Microsoft)**
  - `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
  - `GET /api/auth/sso/{provider}`, `GET /api/auth/sso/{provider}/callback`
  - JWT HS256, bcrypt passwords, signed state token for SSO CSRF protection
  - User model extended: `sso_provider`, `sso_sub` with unique constraint
- [x] **Alembic initial migration** — all 13 tables in `versions/001_initial_schema.py`
- [x] **Workspace CRUD** — `POST/GET/PUT /api/workspaces`, shared email account management
- [x] **Agent CRUD + role prompt** — `POST/GET/PUT/DELETE /api/workspaces/{id}/agents`
  - `allowed_tools` validated against strict allowlist (7 tools)
  - `telegram_bot_token_ref` write-only (never returned in responses)
  - Partial update (PUT) — only supplied fields changed
  - Container management endpoints (start/stop) with ownership checks
- [x] **Thread + Message CRUD** — `POST/GET /api/workspaces/{id}/threads`, `GET /api/threads/{id}`, `POST/GET /api/threads/{id}/messages`
  - Cursor pagination: opaque base64url `(created_at, id)` cursor — stable, tamper-proof
  - `channel` validated against allowlist: `web|telegram|email|system`
  - `sender_type` hardcoded to `user` for user-posted messages (agent writes go through orchestrator)
  - Thread ownership verified via workspace `user_id` → 404 on non-owner access
- [x] **Orchestrator: step queue + A2A approval gating**
  - `dispatch_step()` creates `TaskStep` + pushes to `agent.{id}` Celery queue
  - `_check_a2a()` queries `approvals` table; scope-validates (agent pair, thread, duration window)
  - `route()` dispatches steps for allowed user→agent messages with task_id
  - Task CRUD: `POST /api/threads/{id}/tasks`, `GET /api/tasks/{id}`, `GET /api/tasks/{id}/steps`, `POST /api/tasks/{id}/cancel`
  - `step_results.py` updates task status to done/failed when all steps are terminal
  - 79/79 tests passing
- [x] **Telegram inbound/outbound** — `POST /api/connectors/telegram/{agent_id}`
  - Inbound: finds/creates thread by chat_id, persists message, creates Task, dispatches to agent queue
  - Outbound: `send_message(bot_token, chat_id, text)` via httpx to Telegram Bot API
  - `telegram_bot_token_ref` = raw token (MVP); `_resolve_token()` is the Vault swap point
  - 88/88 tests passing
- [x] **Email outbound + IMAP inbound polling** (PR #6, feat/email-connector)
  - `send_email(credentials_ref, from_alias, signature?)` via aiosmtplib STARTTLS; RFC 5322 Message-ID; In-Reply-To/References headers
  - `poll_inbox(credentials_ref, since_uid?)` via aioimaplib; UNSEEN fetch for MVP; `_parse_raw_email()` extracts body + headers
  - `find_or_create_email_thread(db, workspace_id, msg_dict)` — In-Reply-To → References → create new Thread
  - `_poll_account()` (inbox_poll.py): persists Message, creates Task, dispatches to agent queue via Planner + OrchestratorRouter
  - `credentials_ref` = Fernet-encrypted JSON `{smtp_host, smtp_port, imap_host, imap_port, username, password}`
  - aiosmtplib/aioimaplib: lazy imports (Docker-only; not installed locally — same pattern as Docker SDK)
  - 99/99 tests passing (20 new email tests)
- [x] **Role templates: Negotiator, Sourcing Agent, Contractor Liaison** (PR #7)
  - `services/role_templates.py` — 3 frozen `RoleTemplate` dataclasses; `list_templates()` / `get_template(id)`
  - `GET /api/agent-templates` — list all (public, no auth required)
  - `GET /api/agent-templates/{id}` — single template; 404 on unknown id
  - Each template: `role_prompt` (250–500 words), `allowed_tools`, `rate_limit_per_min`, `max_concurrency`
  - 116/116 tests passing (17 new template tests)

### Phase 2 — V1 (in progress)
- [x] **Production containerization** (PR #8)
  - `apps/agent/Dockerfile`: fixed CMD shell-form for `$AGENT_ID` expansion; fixed file ownership (`chown -R agent:agent /app`)
  - `docker-compose.yml` (dev): added api healthcheck; added `ENCRYPTION_KEY` to orchestrator-beat; fixed `LLM_MAX_TOKENS` default (32768)
  - `docker-compose.prod.yml`: new production compose — image-based (no build context), Redis/Postgres password enforcement, no exposed DB ports, `--workers 4` uvicorn, `restart: always`
  - `Makefile`: fixed test paths (`app/tests/` not `apps/api/app/tests/`); added `prod-build/up/down/migrate/logs` targets
- [x] **Vendor/contractor CRM** (PR #9)
  - `models/vendor.py` — `Vendor` table: workspace_id (FK), name (unique per workspace), email, category, contact_name, phone, website, country, notes, tags (JSON)
  - `db/migrations/versions/002_add_vendors.py` — Alembic migration
  - `services/vendors.py` — `upsert_vendor()`, `list_vendors()`, `get_vendor()`, `delete_vendor()` (upsert matches on `(workspace_id, name)`)
  - `routers/vendors.py` — `GET/POST /api/workspaces/{id}/vendors`, `GET/PUT/DELETE /api/workspaces/{id}/vendors/{vid}`; category validated against allowlist
  - `tasks/vendor_ops.py` — `handle_vendor_upsert` Celery task on orchestrator queue; lazy DB imports for testability
  - Agent `vendor_tool.py` — implemented: posts to orchestrator queue via Celery `send_task()` (agents never reach Postgres)
  - 143/143 tests passing (18 new vendor tests)
- [ ] Multi-language translation tool
- [x] **Scheduler + follow-ups** (PR #10)
  - `services/orchestrator/scheduler.py` — `Scheduler.schedule_followup()` creates Celery ETA task; `cancel_followup()` calls `celery.control.revoke()`; schedule_id = Celery async result ID
  - `tasks/followups.py` — `handle_schedule_request` Celery task (finds active task for thread, delegates to Scheduler); `fire_followup` ETA task (creates new TaskStep, dispatches to agent queue via OrchestratorRouter)
  - Agent `scheduler_tool.py` — implemented: posts `handle_schedule_request` to orchestrator queue via Celery `send_task()`
  - 152/152 tests passing (9 new scheduler tests)
- [ ] Email provider OAuth (Gmail/Graph)
- [ ] Observability: traces, step-level debugging, `GET /api/tasks/{id}/trace`
- [ ] Policy hardening: detect commitment/contract/payment language → auto-approval gate

---

## Key Engineering Risks

| Risk | Mitigation |
|---|---|
| Agent policy bypass | Sandbox + tool-only execution, no internal network access |
| Email deliverability & rate limits | Per-provider caps, domain allow/deny lists, audit trail |
| Thread integrity across channels | Unified thread model with channel-specific metadata |
| Long-running negotiations | Temporal workflows, idempotency keys, state machine |
| Safety & compliance | Approval workflow, audit logs, recipient controls, PII redaction |

---

## Working Style
- **Never prompt for confirmation mid-task.** Do the full implementation. Only ask right before final testing.
- **Update CLAUDE.md** when architecture changes.
- **Update DEV_LOG.md** at the end of every meaningful session.

### Development Cycle (enforced — every feature)

```
1. git checkout main && git pull origin main   ← start from up-to-date main
2. git checkout -b feat/<feature-name>         ← feature branch
3. /auto <task description> --mode feature     ← implement + test
4. Update CLAUDE.md, DEV_LOG.md, agent-orchestrator.md
5. Commit all changes (code + docs together)
6. git push && gh pr create                    ← PR at end of EVERY cycle
   ↓
   User merges PR
   ↓
7. git checkout main && git pull               ← next cycle starts here
```

**Rules:**
- Every cycle ends with a PR — no exceptions.
- Docs (CLAUDE.md, DEV_LOG.md, agent-orchestrator.md) updated in the same commit as the code.
- Never start a new feature branch until `main` is pulled after the previous PR merges.
- PR description must include: endpoints added, test count, security notes.

### LLM Provider Config (change `LLM_MODEL` only — no code change, no rebuild)
```
LLM_MODEL=anthropic/claude-opus-4-6    LLM_API_KEY=sk-ant-...   LLM_MAX_TOKENS=32768
LLM_MODEL=gpt-4o                        LLM_API_KEY=sk-...
LLM_MODEL=gemini/gemini-1.5-pro         LLM_API_KEY=AIza...
LLM_MODEL=groq/llama-3.3-70b-versatile  LLM_API_KEY=gsk_...
LLM_MODEL=ollama/llama3.3               LLM_API_BASE=http://ollama:11434
```

**Active subscription**: Anthropic API — `claude-opus-4-6` (200K input context, 32K output tokens).
`LLM_MAX_TOKENS` default updated to `32768` in agent runner and `.env.example`.

## Container Rules (Enforced)

- **Agents MUST run in containers** — no in-process agent execution, ever.
- **Agent containers on `agent-net` only** — never add `backend-net` to an agent service.
- **One container per agent** — `AGENT_ID` env var determines the queue (`agent.{AGENT_ID}`).
- **Agents are non-root** — `USER agent` in Dockerfile.
- **Agents never hold credentials** — they post requests to Redis; orchestrator executes with Vault-resolved creds.
- **Scale with**: `make scale-agents N=3` or orchestrator Docker API calls.

## Auth Architecture (Implemented)

```
POST /api/auth/register    → email + password (min 8 chars) → JWT
POST /api/auth/login       → OAuth2PasswordRequestForm (username=email) → JWT
GET  /api/auth/me          → Bearer JWT → UserResponse
GET  /api/auth/sso/{p}     → redirect to Google/GitHub/Microsoft OAuth2 page
GET  /api/auth/sso/{p}/callback → exchange code → find-or-create User → JWT
```

SSO providers: `google`, `github`, `microsoft`
SSO state: signed JWT (HS256, 10-min TTL) — no Redis needed
Link behavior: if SSO email matches existing password account, SSO identity is linked

## SSO Config (env vars)
```
SSO_REDIRECT_BASE_URL=https://your-domain.com
GOOGLE_CLIENT_ID=...          GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...          GITHUB_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...       MICROSOFT_CLIENT_SECRET=...
MICROSOFT_TENANT_ID=common    # or your org tenant ID
```

## Working Rules for Claude

- **Always consult `agent-orchestrator.md`** when uncertain about architecture or requirements.
- **Update this CLAUDE.md** when the plan changes (add features, modify architecture, complete phases).
- **Update `DEV_LOG.md`** after every meaningful development session — what was built, decisions made, what's next.
- Prefer FastAPI + Postgres patterns unless user specifies otherwise.
- Never store secrets in plaintext — always use `credentials_ref` pattern.
- Write tests in `apps/api/app/tests/` — prioritize `test_policy.py`, `test_auth.py`, `test_orchestrator.py`.
- Keep the A2A policy enforcement in `services/orchestrator/policy.py` — do not duplicate it elsewhere.
- Use `Optional[X]` instead of `X | None` in SQLAlchemy `Mapped` columns for Python 3.9 compat.
