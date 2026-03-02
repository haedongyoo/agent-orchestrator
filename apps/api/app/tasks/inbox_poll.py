"""
Inbox Poll — Celery beat task that polls all active shared email inboxes.

Runs every 120s (configured in worker.py beat_schedule).
For each workspace's SharedEmailAccount:
  1. Connects via IMAP (credentials resolved from Vault)
  2. Fetches unseen messages since last poll
  3. Matches them to open threads by email In-Reply-To / References headers
  4. Persists new messages and dispatches tasks to the orchestrator
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
    Poll a single email account, persist new messages, and dispatch tasks.

    Thread matching strategy (in priority order):
      1. In-Reply-To header → match Thread.linked_email_thread_id
      2. First entry in References header → match Thread.linked_email_thread_id
      3. No match → create a new Thread linked to this message's Message-ID
    """
    from app.db.session import AsyncSessionLocal
    from app.models.message import Message
    from app.models.task import Task
    from app.models.workspace import Workspace
    from app.services.connectors.email import find_or_create_email_thread, poll_inbox
    from app.services.orchestrator.planner import Planner
    from app.services.orchestrator.router import OrchestratorRouter
    from sqlalchemy import select

    log.debug("inbox_poll.account", account_id=str(account.id), alias=account.from_alias)

    # Fetch new messages (MVP: always fetch UNSEEN; production: track last UID per account)
    try:
        messages = await poll_inbox(account.credentials_ref)
    except Exception as exc:
        log.error("inbox_poll.poll_failed", account_id=str(account.id), error=str(exc))
        return

    if not messages:
        return

    async with AsyncSessionLocal() as db:
        # Resolve workspace owner for Task.created_by FK
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == account.workspace_id)
        )
        ws = ws_result.scalar_one_or_none()
        if ws is None:
            log.warning("inbox_poll.workspace_missing", account_id=str(account.id))
            return

        for msg_dict in messages:
            try:
                thread = await find_or_create_email_thread(db, account.workspace_id, msg_dict)

                # Persist the inbound message
                db.add(Message(
                    thread_id=thread.id,
                    sender_type="external",
                    sender_id=None,
                    channel="email",
                    content=msg_dict["body"],
                    metadata_={
                        "email_message_id": msg_dict["message_id"],
                        "from": msg_dict["from"],
                        "to": msg_dict["to"],
                        "subject": msg_dict["subject"],
                        "date": msg_dict["date"],
                        "in_reply_to": msg_dict.get("in_reply_to"),
                        "imap_uid": msg_dict["uid"],
                    },
                ))
                await db.flush()

                # Create a task so the orchestrator can decide how to handle the email
                objective = f"Inbound email from {msg_dict['from']}: {msg_dict['subject']}"
                task = Task(
                    workspace_id=account.workspace_id,
                    thread_id=thread.id,
                    objective=objective,
                    status="queued",
                    created_by=ws.user_id,
                )
                db.add(task)
                await db.flush()

                # Dispatch to agent queue via Planner + OrchestratorRouter
                # (no specific agent_id for email — planner picks based on thread context)
                planner = Planner(db)
                steps = await planner.decompose(task, [])   # empty → planner selects agents
                orch = OrchestratorRouter(db)
                for step in steps:
                    orch.enqueue_existing_step(step, workspace_id=account.workspace_id)

                task.status = "running"

            except Exception as exc:
                log.error(
                    "inbox_poll.message_error",
                    account_id=str(account.id),
                    uid=msg_dict.get("uid"),
                    error=str(exc),
                )
                await db.rollback()
                return

        await db.commit()
        log.info(
            "inbox_poll.persisted",
            account_id=str(account.id),
            count=len(messages),
        )


