"""
Inbox Poll — Celery beat task that polls all active shared email inboxes.

Runs every 120s (configured in worker.py beat_schedule).
For each workspace's SharedEmailAccount:
  1. Connects via IMAP (credentials resolved from Vault)
  2. Fetches unseen messages since last poll
  3. Matches them to open threads by email thread headers
  4. Persists new messages and notifies the orchestrator
"""
from __future__ import annotations

import asyncio
import structlog

from app.worker import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.tasks.inbox_poll.poll_all_inboxes")
def poll_all_inboxes() -> dict:
    """Poll all active shared email inboxes for new messages."""
    log.info("inbox_poll.start")
    count = asyncio.run(_poll())
    log.info("inbox_poll.done", accounts_checked=count)
    return {"accounts_checked": count}


async def _poll() -> int:
    from app.db.session import AsyncSessionLocal
    from app.models.workspace import SharedEmailAccount
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SharedEmailAccount).where(SharedEmailAccount.is_active == True)  # noqa: E712
        )
        accounts = result.scalars().all()

        for account in accounts:
            try:
                await _poll_account(account)
            except Exception as exc:
                log.error(
                    "inbox_poll.account_error",
                    account_id=str(account.id),
                    error=str(exc),
                )

        return len(accounts)


async def _poll_account(account) -> None:
    """
    Poll a single email account.
    TODO: resolve credentials from Vault, connect via aioimaplib,
    fetch unseen messages, match to threads, persist messages.
    """
    log.debug("inbox_poll.account", account_id=str(account.id), alias=account.from_alias)
    # TODO: implement IMAP polling
