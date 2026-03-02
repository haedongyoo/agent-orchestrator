# OpenClaw Agent Orchestrator — CLAUDE.md

This file is the authoritative project reference for Claude Code. Read this before making any changes.
**Source of truth**: `agent-orchestrator.md`. Keep this file in sync with the plan.

---

## Project Goal

Build **OpenClaw Agents** — a service that runs multiple AI agents as "always-on employees" for 24/7 negotiation, sourcing, and workflow automation (furniture suppliers, material factories, local contractors, multi-language).

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
- [ ] Auth + workspace CRUD
- [ ] Agent CRUD + role prompt
- [ ] Web thread chat + message persistence
- [ ] Telegram inbound/outbound (single bot per agent)
- [ ] Email outbound + basic inbound polling (IMAP)
- [ ] Orchestrator: step queue + approval flow for A2A messages
- [ ] 2–3 role templates (negotiator / sourcing / contractor)

### Phase 2 — V1
- [ ] Vendor/contractor CRM
- [ ] Multi-language translation tool
- [ ] Robust scheduler for follow-ups
- [ ] Email provider OAuth (Gmail/Graph)
- [ ] Observability: traces, step-level debugging, replay
- [ ] Policy hardening: approval required for contract/commitment/payment language

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

### LLM Provider Config (change `LLM_MODEL` only — no code change, no rebuild)
```
LLM_MODEL=anthropic/claude-opus-4-6    LLM_API_KEY=sk-ant-...
LLM_MODEL=gpt-4o                        LLM_API_KEY=sk-...
LLM_MODEL=gemini/gemini-1.5-pro         LLM_API_KEY=AIza...
LLM_MODEL=groq/llama-3.3-70b-versatile  LLM_API_KEY=gsk_...
LLM_MODEL=ollama/llama3.3               LLM_API_BASE=http://ollama:11434
```

## Container Rules (Enforced)

- **Agents MUST run in containers** — no in-process agent execution, ever.
- **Agent containers on `agent-net` only** — never add `backend-net` to an agent service.
- **One container per agent** — `AGENT_ID` env var determines the queue (`agent.{AGENT_ID}`).
- **Agents are non-root** — `USER agent` in Dockerfile.
- **Agents never hold credentials** — they post requests to Redis; orchestrator executes with Vault-resolved creds.
- **Scale with**: `make scale-agents N=3` or orchestrator Docker API calls.

## Working Rules for Claude

- **Always consult `agent-orchestrator.md`** when uncertain about architecture or requirements.
- **Update this CLAUDE.md** when the plan changes (add features, modify architecture, complete phases).
- **Update `DEV_LOG.md`** after every meaningful development session — what was built, decisions made, what's next.
- Prefer FastAPI + Postgres patterns unless user specifies otherwise.
- Never store secrets in plaintext — always use `credentials_ref` pattern.
- Write tests in `apps/api/app/tests/` — prioritize `test_policy.py` and `test_orchestrator.py`.
- Keep the A2A policy enforcement in `services/orchestrator/policy.py` — do not duplicate it elsewhere.
