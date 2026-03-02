"""
Telegram Connector

Handles:
  - Inbound webhook from Telegram (POST /api/connectors/telegram/{bot_token})
  - Outbound messages via Bot API (send_telegram tool)

Each agent has its own bot token, stored via credentials_ref (never plaintext).
"""
from fastapi import APIRouter, Request, HTTPException
from typing import Any

router = APIRouter()


@router.post("/telegram/{bot_token_hash}")
async def telegram_webhook(bot_token_hash: str, request: Request):
    """
    Receive an update from Telegram.
    bot_token_hash is a short opaque ID that maps to an agent's bot token in Vault.
    """
    payload: dict[str, Any] = await request.json()
    # TODO:
    # 1. Resolve bot_token_hash → agent_id + workspace_id
    # 2. Extract message text + chat_id
    # 3. Persist as inbound Message on the linked thread
    # 4. Trigger orchestrator to generate agent response
    return {"ok": True}


async def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    thread_id: str | None = None,
) -> dict:
    """
    Send a message via the Telegram Bot API.
    bot_token must be retrieved from Vault at call time — never stored in memory long-term.
    """
    # TODO: use httpx to call https://api.telegram.org/bot{token}/sendMessage
    raise NotImplementedError
