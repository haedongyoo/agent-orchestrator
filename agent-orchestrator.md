# AI Agent Orchestration Service (OpenClaw Agents) — Code Plan (English)

## 0) Goal
Build a service that lets a user configure and run multiple AI agents as “always-on employees.”
- User configures: a shared “throwaway” email inbox, per-agent Telegram identities, user Telegram identity, number of agents, and each agent’s role.
- User can chat with agents via:
  - Telegram (agents talk to the user using their own Telegram identities)
  - Web app (orchestration UI)
  - Conversations can be synchronized between Web and Telegram.
- Agents **cannot talk to each other** without explicit user permission.
- Agents are OpenClaw agents.
- Agents can use email to perform tasks (negotiation, RFQs, follow-ups).

Primary use case: run 24/7 negotiation and sourcing workflows (furniture suppliers, material factories, local contractors) in any language.

---

## 1) Requirements → System Constraints
### 1.1 Communication Rules
- Default: **Agent-to-agent communication is forbidden**.
- Exception: user grants explicit permission via an approval workflow:
  - Scope-limited: which agents, which thread/task, duration, and what can be shared.

### 1.2 Channels
- **Telegram**
  - User Telegram chat_id configured.
  - Each agent can have its own Telegram bot token (recommended) or identity.
- **Web Orchestration UI**
  - Real-time chat with agents.
  - Optional sync to/from Telegram for the same thread.
- **Email**
  - One shared “generic inbox” (e.g., procurement@domain) usable by agents.
  - Outbound and inbound messages attach to a thread/task.

### 1.3 Multi-Agent Execution
- N agents created per workspace.
- Each agent has:
  - Role prompt
  - Allowed tools
  - Channel permissions
  - Rate limits / concurrency
- Long-running operations require:
  - Job queue + scheduler
  - Task state machine

---

## 2) High-Level Architecture
### 2.1 Components
1) **API Server** (FastAPI / NestJS)
- Auth, settings CRUD, threads/messages, tasks, approvals, audit logs

2) **Orchestrator**
- Decides which agent acts next, routes events, enforces policy
- Creates/dispatches steps and schedules follow-ups

3) **Agent Runtime (OpenClaw)**
- Runs each agent with a sandboxed tool layer
- No direct network calls to other agents (prevents bypassing policy)

4) **Connectors**
- Telegram connector (webhook/long polling, routes by bot token)
- Email connector (IMAP/Graph/Gmail API; OAuth preferred)
- Web chat connector (WebSocket/SSE)

5) **Queue + Scheduler**
- Redis Queue / Celery / BullMQ / **Temporal** (recommended for long workflows)

6) **Database**
- Postgres recommended

7) **Policy Engine**
- Enforces “no agent-to-agent without approval”
- Optional: enforce “approval required before emailing new recipients”
- Domain allow/deny lists, rate limits, and safety constraints

---

## 3) Minimal Data Model (Schema Draft)
### 3.1 Identity / Auth
- `users`: id, email, password_hash (nullable), sso_provider (nullable), sso_sub (nullable), is_active, created_at
  - `sso_provider` ∈ {`google`, `github`, `microsoft`} — null for password accounts
  - `sso_sub` — stable provider-unique user ID (never changes)
  - Unique constraint on `(sso_provider, sso_sub)` — prevents duplicate SSO identities
  - Account linking: if SSO email matches an existing password account, SSO identity is silently linked
- `workspaces`: id, user_id, name, timezone, language_pref

### 3.2 Channel Configuration
- `user_channels`:
  - workspace_id
  - user_telegram_chat_id (nullable)
  - web_chat_enabled (bool)

- `shared_email_accounts`:
  - workspace_id
  - provider_type (imap/gmail/graph)
  - credentials_ref (encrypted secret reference)
  - from_alias, signature_template

- `agents`:
  - id, workspace_id
  - name
  - role_prompt
  - allowed_tools (json)
  - telegram_bot_token_ref (nullable)
  - is_enabled
  - rate_limit_per_min
  - max_concurrency

### 3.3 Conversations
- `threads`:
  - id, workspace_id
  - title
  - status (open/closed)
  - linked_telegram_chat_id (nullable)
  - linked_email_thread_id (nullable)

- `messages`:
  - id, thread_id
  - sender_type (user/agent/system/external)
  - sender_id (user_id/agent_id/null)
  - channel (web/telegram/email/system)
  - content (text)
  - metadata (json: language, attachments, email headers)
  - created_at

### 3.4 Tasks / Steps
- `tasks`:
  - id, workspace_id, thread_id
  - objective (text)
  - status (queued/running/blocked/needs_approval/done/failed)
  - created_by (user_id)
  - created_at

- `task_steps`:
  - id, task_id
  - agent_id
  - step_type (plan/action/message)
  - tool_call (json)
  - result (json)
  - status (queued/running/done/failed)
  - created_at

### 3.5 Approvals + Audit
- `approvals`:
  - id, workspace_id, thread_id, task_id (nullable)
  - approval_type (enable_agent_chat/send_email/new_recipient/share_info/other)
  - requested_by (agent_id/system)
  - approved_by (user_id nullable)
  - scope (json: agents, duration, recipients, thread limits)
  - status (pending/approved/rejected)
  - created_at, decided_at

- `audit_logs`:
  - id, workspace_id
  - actor_type (user/agent/system)
  - actor_id
  - action
  - target_type, target_id
  - detail (json)
  - created_at

---

## 4) API Design (Example)
### 4.1 Workspace & Settings
- `POST /api/workspaces`
- `GET /api/workspaces/{id}`
- `PUT /api/workspaces/{id}`
- `POST /api/workspaces/{id}/shared-email`
- `PUT /api/workspaces/{id}/shared-email/{emailId}`
- `POST /api/workspaces/{id}/agents`
- `GET /api/workspaces/{id}/agents`
- `PUT /api/workspaces/{id}/agents/{agentId}`
- `DELETE /api/workspaces/{id}/agents/{agentId}`

### 4.2 Threads & Messages
- `POST /api/workspaces/{id}/threads`
- `GET /api/threads/{threadId}`
- `POST /api/threads/{threadId}/messages` (user message)
- `GET /api/threads/{threadId}/messages?cursor=...`

### 4.3 Tasks
- `POST /api/threads/{threadId}/tasks` (create objective)
- `GET /api/tasks/{taskId}`
- `POST /api/tasks/{taskId}/cancel`

### 4.4 Approvals
- `GET /api/workspaces/{id}/approvals?status=pending`
- `POST /api/approvals/{approvalId}/approve`
- `POST /api/approvals/{approvalId}/reject`

### 4.5 Realtime
- `WS /ws/threads/{threadId}`
  - events: new_message, task_status, approval_requested, approval_decided

---

## 5) Orchestration Logic (Core Behavior)
### 5.1 Basic Flow
1) User sends objective in a thread:
   - “Contact furniture suppliers worldwide, request quotes, negotiate pricing.”
2) System creates a task + initial plan step.
3) Orchestrator assigns steps to agents based on roles:
   - Agent A: global furniture suppliers negotiation
   - Agent B: material sourcing factories negotiation
   - Agent C: local contractor negotiation
4) Agents perform actions via tools (email/telegram/web message).
5) Incoming replies (email/telegram) get appended to the thread.
6) Orchestrator reacts to new inbound messages and generates follow-up steps.
7) Scheduler triggers periodic follow-ups (e.g., “if no reply in 24h, ping again”).

### 5.2 Enforcing “No Agent-to-Agent Chat Without Permission”
**All message routing goes through a single router** in the orchestrator:
- If sender=agent and receiver=agent:
  - Check approvals for scope:
    - thread_id/task_id match
    - agent IDs match
    - approval is active (time window)
    - content type allowed (e.g., summary only)
  - If not approved:
    - Create an `approval` row (pending)
    - Block the route and notify user in UI (“Agent A requests to share info with Agent B”)

### 5.3 Preventing Bypasses
- OpenClaw agents must be sandboxed:
  - Only allowed tools can be used
  - No direct access to internal service network endpoints
- Network controls:
  - Separate service accounts / ACLs
  - Agents cannot call each other directly

### 5.4 Parallelism
- Convert outreach into a “contact plan”:
  - N vendors → N outreach steps
- Worker pool processes steps concurrently.
- Orchestrator enforces:
  - per-agent concurrency
  - per-provider email send rate limits
  - global backpressure and retries

---

## 6) OpenClaw Agent Design
### 6.1 Standard Prompt Template
- **System**: policies (no agent-to-agent), required approvals, safety and logging
- **Role**: agent mission (negotiator, sourcing, contractor liaison)
- **Context**:
  - workspace settings (company info, signature, tone)
  - thread history (summarized)
  - vendor list / constraints (budget, timeline, materials, shipping)
- **Tools**: email, telegram, web-chat, approvals, vendor db

### 6.2 Internal Tooling Contracts (Examples)
- `request_approval(type, scope, reason) -> approval_id`
- `send_email(to, subject, body, thread_id, attachments?) -> message_id`
- `read_email_inbox(thread_id or mailbox_ref) -> messages`
- `send_telegram(chat_id, text, thread_id) -> message_id`
- `post_web_message(thread_id, text) -> message_id`
- `upsert_vendor(profile) -> vendor_id`
- `schedule_followup(task_id, when, payload) -> schedule_id`

---

## 7) Security & Governance (Non-Negotiable)
### 7.1 Credentials Storage
- Never store bot tokens or email credentials in plaintext DB.
- Use Vault/KMS:
  - DB holds `credentials_ref` only.

### 7.2 Email Abuse Controls
- Default policies:
  - approval required for new recipients (optional but recommended)
  - domain allow/deny lists
  - outbound volume caps (daily/hourly)
- Audit trails for every outbound message:
  - which agent, which approval, which task

### 7.3 Data Protection
- PII redaction for logs
- Per-workspace data separation
- Export/delete support for compliance

---

## 8) UX Plan (Setup + Operations Console)
### 8.1 Setup Page
- Connect shared email (test send + inbox read test)
- Set user Telegram chat_id (user sends `/start` to a bot)
- Create agents:
  - name, role template, tool permissions
  - connect Telegram bot token (test message)
- Policy toggles:
  - agent-to-agent communication default OFF
  - approval requirements for outbound email

### 8.2 Operations
- Unified thread timeline:
  - Web + Telegram + Email messages in one feed
- Task dashboard:
  - step list, status, next scheduled follow-up, retries
- Approvals inbox:
  - approve/reject agent requests (share info, contact new recipients, etc.)

---

## 9) Implementation Phases
### 9.1 MVP (Fastest Path)
- [x] Auth + Alembic initial migration (2026-03-01)
  - Email/password registration + login (bcrypt + HS256 JWT)
  - SSO: Google, GitHub, Microsoft (OAuth2 Authorization Code Flow)
  - JWT state CSRF protection (avoids Redis coupling)
  - Account linking: SSO email → existing password account
  - `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
  - `/api/auth/sso/{provider}`, `/api/auth/sso/{provider}/callback`
  - Alembic migration: all 13 tables + indexes in FK-dependency order
- [x] Workspace CRUD (2026-03-01)
  - `POST/GET/PUT /api/workspaces`, shared email account `POST/PUT`
  - Workspace access owner-scoped; `credentials_ref` write-only
- [x] Agent CRUD + role prompt (2026-03-01)
  - `POST/GET/PUT/DELETE /api/workspaces/{id}/agents`
  - `allowed_tools` allowlist: send_email, read_email_inbox, send_telegram, post_web_message, request_approval, upsert_vendor, schedule_followup
  - Container management endpoints (start/stop) with ownership enforcement
- [x] Web thread chat + message persistence (2026-03-01)
  - `POST/GET /api/workspaces/{id}/threads`, `GET /api/threads/{id}`
  - `POST /api/threads/{id}/messages`, `GET /api/threads/{id}/messages`
  - Cursor pagination: `(created_at, id)` keyset — stable, tamper-proof base64url encoding
- [x] Telegram inbound/outbound (single bot per agent)
  - Inbound: POST /api/connectors/telegram/{agent_id} → find/create thread, persist message, create Task, dispatch to agent queue
  - Outbound: send_message(bot_token, chat_id, text) via httpx → Telegram Bot API
  - Helpers: register_webhook(), delete_webhook()
  - Thread auto-created per (workspace_id, chat_id); reused on subsequent messages
- [x] Email outbound + basic inbound polling (IMAP) (2026-03-01)
  - Outbound: send_email(credentials_ref, from_alias, signature) via aiosmtplib STARTTLS; MIME + threading headers
  - Inbound: poll_inbox(credentials_ref, since_uid?) via aioimaplib; UNSEEN fetch for MVP
  - find_or_create_email_thread: In-Reply-To → References → new Thread (linked_email_thread_id)
  - _poll_account(): resolves workspace owner, persists Message, creates Task, dispatches to agent queue
- [x] Orchestrator:
  - step queue (dispatch_step → agent.{id} Redis queue via Celery)
  - A2A approval gating (policy.py queries approvals table; scope-checked by agent pair, thread, duration)
  - task status state machine (step_results.py updates task done/failed when all steps terminal)
  - task CRUD endpoints: POST/GET /tasks, GET /tasks/{id}/steps, POST /tasks/{id}/cancel
- [ ] Provide 2–3 role templates (negotiator/sourcing/contractor)

### 9.2 V1
- Vendor/contractor CRM
- Multi-language translation tool
- Robust scheduler for follow-ups
- Email provider OAuth integration (Gmail/Graph)
- Observability: traces, step-level debugging, replay
- Policy hardening:
  - always require approval for contract/commitment/payment language

---

## 9.4) LLM Subscription (Updated 2026-03-01)

**Provider**: Anthropic API
**Model**: `claude-opus-4-6` (`anthropic/claude-opus-4-6` via LiteLLM)
**Context**: 200K input tokens, 32K output tokens
**`LLM_MAX_TOKENS`**: `32768` (updated from `4096`)

Set via env vars — no code change required to switch provider. See `.env.example`.

---

## 9.5) Auth Architecture (Implemented 2026-03-01)

### Token Format
- HS256 JWT, `sub` = `str(user.id)`, configurable expiry (default 30 min via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- All tokens validated by `get_current_user` FastAPI dependency in `services/auth.py`

### SSO Flow (stateless — no Redis required)
1. `GET /api/auth/sso/{provider}` → generate signed JWT state (10-min TTL, `HS256`) → 302 redirect to provider
2. `GET /api/auth/sso/{provider}/callback?code=...&state=...`
   - Verify state JWT (provider match + expiry)
   - POST code to provider token endpoint → access_token
   - GET user profile (email, stable sub ID)
   - GitHub: follow-up `/user/emails` call if profile email is private
   - Find-or-create user → return JWT

### Required Config (env vars)
```
SECRET_KEY=<random 32+ char string>
SSO_REDIRECT_BASE_URL=https://api.yourdomain.com
GOOGLE_CLIENT_ID=...  GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...  GITHUB_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...  MICROSOFT_CLIENT_SECRET=...
MICROSOFT_TENANT_ID=common
```

### Key Files
| File | Purpose |
|------|---------|
| `app/services/auth.py` | JWT create/decode, `get_current_user` dependency |
| `app/services/sso.py` | OAuth2 state, code exchange, user info extraction |
| `app/routers/auth.py` | All `/api/auth/*` endpoints |
| `app/db/migrations/versions/001_initial_schema.py` | All 13 tables |

---

## 10) Recommended Tech Stack (Example: Python)
- API: **FastAPI**
- DB: **Postgres**
- Queue/Scheduler:
  - MVP: Redis + Celery/RQ
  - Production: **Temporal** (strongly recommended for long workflows)
- Realtime: WebSocket (or SSE)
- Telegram: webhook-based bot framework
- Email: IMAP/SMTP for MVP → OAuth provider integration for production
- Agent runtime: OpenClaw in isolated worker processes/containers

---

## 11) Suggested Repo Layout (Python/FastAPI)
repo/
  apps/
    api/
      app/
        main.py
        routers/
          auth.py
          workspaces.py
          agents.py
          threads.py
          tasks.py
          approvals.py
        services/
          orchestrator/
            router.py
            planner.py
            policy.py
            scheduler.py
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
        tests/
          test_policy.py
          test_orchestrator.py
          test_connectors.py

---

## 12) Key Engineering Risks (Plan for Them Early)
- Preventing agent bypass of policy (sandboxing + tool-only execution)
- Email deliverability and rate limits
- Maintaining conversation-thread integrity across Telegram + email + web
- Long-running negotiations: retries, idempotency, and state management
- Safety and compliance: approvals, audit logs, recipient controls







