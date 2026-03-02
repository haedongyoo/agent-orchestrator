"""
Email Connector

Handles:
  - Outbound: send_email tool (SMTP/OAuth)
  - Inbound: poll_inbox background task (IMAP/OAuth)

Credentials are always fetched from Vault at call time via credentials_ref.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class OutboundEmail:
    to: List[str]
    subject: str
    body: str
    thread_id: str           # internal thread reference
    attachments: Optional[List[dict]] = None
    reply_to_message_id: Optional[str] = None  # for email threading


async def send_email(
    email: OutboundEmail,
    credentials_ref: str,    # vault/kms reference to SMTP credentials
    from_alias: str,
    signature: str = "",
) -> str:
    """
    Send an email. Returns the sent message ID.
    Credentials are resolved from Vault at call time.
    """
    # TODO:
    # 1. Resolve credentials_ref → SMTP host/port/user/pass from Vault
    # 2. Construct MIME message with reply-to threading headers
    # 3. Send via aiosmtplib
    # 4. Return message-id header
    raise NotImplementedError


async def poll_inbox(
    credentials_ref: str,
    mailbox: str = "INBOX",
    since_uid: Optional[int] = None,
) -> List[dict]:
    """
    Poll IMAP inbox for new messages since last known UID.
    Returns list of raw message dicts for the orchestrator to process.
    """
    # TODO:
    # 1. Resolve credentials_ref → IMAP host/port/user/pass from Vault
    # 2. Connect via aioimaplib
    # 3. Fetch unseen messages since since_uid
    # 4. Parse and return
    raise NotImplementedError
