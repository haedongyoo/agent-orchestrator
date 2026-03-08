from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.db.session import engine, Base
from app.routers import auth, workspaces, agents, threads, tasks, approvals, llm_configs, role_templates, vendors, email_oauth
from app.services.connectors import telegram, webchat


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="OpenClaw Agent Orchestrator",
    version="0.1.0",
    description="AI Agent Orchestration Service — run multiple agents as always-on employees.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router,        prefix="/api/auth",       tags=["auth"])
app.include_router(workspaces.router,  prefix="/api/workspaces", tags=["workspaces"])
app.include_router(agents.router,      prefix="/api/workspaces", tags=["agents"])
app.include_router(threads.router,     prefix="/api",            tags=["threads"])
app.include_router(tasks.router,       prefix="/api",            tags=["tasks"])
app.include_router(approvals.router,   prefix="/api",            tags=["approvals"])
app.include_router(llm_configs.router,      prefix="/api",            tags=["llm-config"])
app.include_router(role_templates.router,   prefix="/api",            tags=["agent-templates"])
app.include_router(vendors.router,          prefix="/api/workspaces", tags=["vendors"])

# ── Connector endpoints (webhooks) ────────────────────────────────────────────
app.include_router(telegram.router,    prefix="/api/connectors", tags=["connectors"])
app.include_router(webchat.router,     prefix="/ws",             tags=["websocket"])
app.include_router(email_oauth.router, prefix="/api/email-oauth", tags=["email-oauth"])


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": app.version}
