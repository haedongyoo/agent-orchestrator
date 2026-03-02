"""send_telegram tool.

Like email, the bot token is never held in the agent container.
The agent posts a send_telegram_request event; the orchestrator executes it.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()


async def send_telegram(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    text: str,
    chat_id: str | None = None,
) -> dict:
    """
    Request a Telegram message to be sent.
    The orchestrator resolves the bot token from Vault and sends via Bot API.
    """
    log.info("tool.send_telegram.requested", agent_id=agent_id, chat_id=chat_id)
    # TODO: post send_telegram_request to Redis result queue
    return {
        "status": "queued",
        "chat_id": chat_id,
        "note": "send_telegram request posted to orchestrator queue",
    }
