"""
Telegram Connector

Handles:
  - Inbound webhook from Telegram (POST /api/connectors/telegram/{agent_id})
  - Outbound messages via the Bot API (send_message)
  - Webhook registration / teardown helpers (register_webhook, delete_webhook)

One bot per agent — each agent has its own Telegram bot token stored in
agents.telegram_bot_token_ref.

MVP security note:
  - Webhook path uses the agent UUID, which is opaque (not guessable) but
    does leak the internal agent identifier.
  - Production: compute HMAC(SECRET_KEY, bot_token)[:16] and store that as
    the path segment, fully decoupling it from internal IDs.

MVP token note:
  - telegram_bot_token_ref is stored as the raw bot token string (plaintext).
  - Production: treat the field as a Vault path reference and call
    _resolve_token() to do a Vault read at request time.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.agent import Agent
from app.models.message import Message
from app.models.task import Task
from app.models.thread import Thread
from app.models.workspace import Workspace
from app.services.orchestrator.planner import Planner
from app.services.orchestrator.router import OrchestratorRouter

router = APIRouter()

_TELEGRAM_API = "https://api.telegram.org"


# ── Inbound webhook ────────────────────────────────────────────────────────────

@router.post("/telegram/{agent_id}", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Receive a Telegram Update and route it to the agent's processing queue.

    Always returns {"ok": true} — Telegram requires a 200 response within
    60 s or it retries the delivery. Errors are swallowed to prevent retries
    for non-retryable conditions (missing agent, non-text update).
    """
    payload: dict[str, Any] = await request.json()

    # Resolve agent — 200 even on miss so Telegram doesn't hammer a dead webhook
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        return {"ok": True, "detail": "agent_not_found"}

    # Only handle plain text messages for MVP
    msg = payload.get("message") or payload.get("edited_message")
    if msg is None or "text" not in msg:
        return {"ok": True, "detail": "ignored_update_type"}

    chat_id = str(msg["chat"]["id"])
    text: str = msg["text"]
    telegram_message_id: Optional[int] = msg.get("message_id")

    # Find or create a thread linked to this chat
    thread = await _find_or_create_thread(db, agent, chat_id, text)

    # Persist the inbound message
    db.add(Message(
        thread_id=thread.id,
        sender_type="external",
        sender_id=None,
        channel="telegram",
        content=text,
        metadata_={
            "telegram_message_id": telegram_message_id,
            "chat_id": chat_id,
        },
    ))
    await db.flush()

    # Resolve workspace owner so Task.created_by satisfies the FK constraint
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == agent.workspace_id)
    )
    ws = ws_result.scalar_one_or_none()
    if ws is None:
        # Workspace deleted mid-request — nothing more to do
        await db.rollback()
        return {"ok": True, "detail": "workspace_not_found"}

    # Create a task and dispatch it to the agent's processing queue
    task = Task(
        workspace_id=agent.workspace_id,
        thread_id=thread.id,
        objective=text,
        status="queued",
        created_by=ws.user_id,
    )
    db.add(task)
    await db.flush()

    planner = Planner(db)
    steps = await planner.decompose(task, [agent.id])

    orch = OrchestratorRouter(db)
    for step in steps:
        orch.enqueue_existing_step(step, workspace_id=agent.workspace_id)

    task.status = "running"
    await db.commit()

    return {"ok": True}


# ── Outbound API ───────────────────────────────────────────────────────────────

async def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    reply_to_message_id: Optional[int] = None,
) -> dict:
    """
    Send a text message via the Telegram Bot API.

    bot_token must be the raw token (resolved from telegram_bot_token_ref
    by the caller — never cache the token in memory long-term).

    Returns the Telegram API response dict on success.
    Raises httpx.HTTPStatusError on 4xx/5xx responses.
    """
    url = f"{_TELEGRAM_API}/bot{bot_token}/sendMessage"
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_to_message_id is not None:
        body["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=body)
        response.raise_for_status()
        return response.json()


async def register_webhook(bot_token: str, webhook_url: str) -> dict:
    """
    Register a Telegram webhook URL for this bot.
    Call this after setting a bot token on an agent.

    webhook_url example:
        https://api.example.com/api/connectors/telegram/{agent_id}
    """
    url = f"{_TELEGRAM_API}/bot{bot_token}/setWebhook"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json={"url": webhook_url})
        response.raise_for_status()
        return response.json()


async def delete_webhook(bot_token: str) -> dict:
    """Remove the Telegram webhook for a bot (e.g. when disabling an agent)."""
    url = f"{_TELEGRAM_API}/bot{bot_token}/deleteWebhook"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url)
        response.raise_for_status()
        return response.json()


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _find_or_create_thread(
    db: AsyncSession,
    agent: Agent,
    chat_id: str,
    first_message: str,
) -> Thread:
    """
    Return the Thread already linked to this Telegram chat, or create a new one.
    Threads are scoped to (workspace_id, chat_id) to support multi-agent workspaces.
    """
    result = await db.execute(
        select(Thread).where(
            Thread.workspace_id == agent.workspace_id,
            Thread.linked_telegram_chat_id == chat_id,
        )
    )
    thread = result.scalar_one_or_none()
    if thread:
        return thread

    title = (first_message[:97] + "...") if len(first_message) > 100 else first_message
    thread = Thread(
        workspace_id=agent.workspace_id,
        title=title or f"Telegram: {chat_id}",
        linked_telegram_chat_id=chat_id,
    )
    db.add(thread)
    await db.flush()
    return thread


def _resolve_token(agent: Agent) -> str:
    """
    Return the raw bot token for this agent.
    MVP: telegram_bot_token_ref stores the token directly (plaintext).
    Production: replace with a Vault read using the ref as a path.
    """
    if not agent.telegram_bot_token_ref:
        raise ValueError(f"Agent {agent.id} has no Telegram bot token configured")
    return agent.telegram_bot_token_ref
