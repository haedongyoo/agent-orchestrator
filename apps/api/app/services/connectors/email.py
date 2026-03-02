"""
Email Connector

Handles:
  - Outbound: send_email — SMTP via aiosmtplib
  - Inbound:  poll_inbox — IMAP via aioimaplib

MVP credential storage:
  credentials_ref is a Fernet-encrypted JSON blob (see services/secrets.py):
  {
    "smtp_host": "smtp.example.com",   (optional — falls back to config.smtp_host)
    "smtp_port": 587,                  (optional — falls back to config.smtp_port)
    "imap_host": "imap.example.com",   (optional — falls back to config.imap_host)
    "imap_port": 993,                  (optional — falls back to config.imap_port)
    "username":  "user@example.com",
    "password":  "secret"
  }

  Production: replace _resolve_credentials() with a Vault Transit read
  using credentials_ref as the secret path.
"""
from __future__ import annotations

import email as email_lib
import json
import uuid
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import structlog

from app.config import settings
from app.services.secrets import decrypt_api_key

log = structlog.get_logger()


# ── Outbound data model ────────────────────────────────────────────────────────

@dataclass
class OutboundEmail:
    to: List[str]
    subject: str
    body: str
    thread_id: str                          # internal thread reference
    attachments: Optional[List[dict]] = None
    reply_to_message_id: Optional[str] = None   # RFC 5322 Message-ID for threading


# ── Credential resolution ──────────────────────────────────────────────────────

def _resolve_credentials(credentials_ref: str) -> dict:
    """
    Decrypt and parse SMTP/IMAP credentials from a Fernet-encrypted JSON blob.

    MVP: credentials_ref IS the encrypted token.
    Production: treat credentials_ref as a Vault path and do a Vault read.
    """
    raw = decrypt_api_key(credentials_ref)
    return json.loads(raw)


# ── Outbound SMTP ──────────────────────────────────────────────────────────────

async def send_email(
    email: OutboundEmail,
    credentials_ref: str,
    from_alias: str,
    signature: str = "",
) -> str:
    """
    Send an email via SMTP (STARTTLS).
    Returns the RFC 5322 Message-ID of the sent message.

    Credentials are resolved from Vault at call time — never cached long-term.
    Raises aiosmtplib.SMTPException on delivery failure.
    """
    creds = _resolve_credentials(credentials_ref)

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = from_alias
    msg["To"] = ", ".join(email.to)
    msg["Subject"] = email.subject

    # Stable RFC 5322 Message-ID for email threading
    domain = from_alias.split("@")[-1] if "@" in from_alias else "mail.local"
    message_id = f"<{uuid.uuid4()}@{domain}>"
    msg["Message-ID"] = message_id

    # Threading headers (In-Reply-To + References)
    if email.reply_to_message_id:
        msg["In-Reply-To"] = email.reply_to_message_id
        msg["References"] = email.reply_to_message_id

    body_text = f"{email.body}\n\n{signature}" if signature else email.body
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    smtp_host = creds.get("smtp_host") or settings.smtp_host
    smtp_port = int(creds.get("smtp_port", settings.smtp_port))

    import aiosmtplib  # lazy — not installed locally; lives in Docker image
    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=creds["username"],
        password=creds["password"],
        start_tls=True,
    )

    log.info("email.sent", message_id=message_id, to=email.to, subject=email.subject)
    return message_id


# ── Inbound IMAP ───────────────────────────────────────────────────────────────

async def poll_inbox(
    credentials_ref: str,
    mailbox: str = "INBOX",
    since_uid: Optional[int] = None,
) -> List[dict]:
    """
    Poll an IMAP mailbox for new messages.

    If since_uid is given, fetches messages with UID > since_uid (incremental).
    If since_uid is None, fetches all UNSEEN messages.

    Returns a list of parsed message dicts:
    {
      "uid":         int,
      "message_id":  str,   # RFC 5322 Message-ID header
      "from":        str,
      "to":          str,
      "subject":     str,
      "date":        str,
      "body":        str,
      "in_reply_to": str | None,
      "references":  str | None,
    }
    """
    creds = _resolve_credentials(credentials_ref)
    imap_host = creds.get("imap_host") or settings.imap_host
    imap_port = int(creds.get("imap_port", settings.imap_port))

    import aioimaplib  # lazy — not installed locally; lives in Docker image
    client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
    await client.wait_hello_from_server()

    login_resp = await client.login(creds["username"], creds["password"])
    _check_imap_ok(login_resp, "login")

    await client.select(mailbox)

    # Choose search criteria
    if since_uid is not None:
        # UID SEARCH UID (n+1):* — all messages newer than the last seen UID
        search_criteria = f"UID {since_uid + 1}:*"
    else:
        search_criteria = "UNSEEN"

    search_resp = await client.uid("search", None, search_criteria)
    if not _is_ok(search_resp):
        await client.logout()
        return []

    raw_uids = _extract_uid_list(search_resp)
    # Filter: if since_uid is set, some servers echo back since_uid itself
    if since_uid is not None:
        raw_uids = [u for u in raw_uids if int(u) > since_uid]

    messages: List[dict] = []
    for uid in raw_uids:
        try:
            fetch_resp = await client.uid("fetch", uid, "(RFC822)")
            if not _is_ok(fetch_resp):
                continue
            raw_bytes = _extract_message_bytes(fetch_resp)
            if raw_bytes is None:
                log.warning("email.poll.no_body", uid=uid)
                continue
            messages.append(_parse_raw_email(int(uid), raw_bytes))
        except Exception as exc:
            log.warning("email.poll.fetch_error", uid=uid, error=str(exc))

    await client.logout()
    log.info("email.polled", mailbox=mailbox, new_messages=len(messages))
    return messages


# ── IMAP response helpers ──────────────────────────────────────────────────────

def _check_imap_ok(response, operation: str) -> None:
    """Raise RuntimeError if IMAP response is not OK."""
    ok = _is_ok(response)
    if not ok:
        raise RuntimeError(f"IMAP {operation} failed: {response!r}")


def _is_ok(response) -> bool:
    """Return True if IMAP response indicates success."""
    if isinstance(response, tuple):
        return str(response[0]).upper() == "OK"
    # aioimaplib 2.x Command response object
    return str(getattr(response, "result", "")).upper() == "OK"


def _extract_uid_list(response) -> List[str]:
    """Extract space-separated UIDs from a SEARCH response."""
    lines = response[1] if isinstance(response, tuple) else getattr(response, "lines", [])
    if not lines:
        return []
    first = lines[0]
    if isinstance(first, (bytes, bytearray)):
        text = first.decode("ascii", errors="ignore").strip()
    else:
        text = str(first).strip()
    return [u for u in text.split() if u.isdigit()]


def _extract_message_bytes(response) -> Optional[bytes]:
    """
    Extract raw RFC 822 bytes from a FETCH response.

    aioimaplib fetch lines layout:
      [0]  b'1 (RFC822 {size}'   — envelope info
      [1]  <raw message bytes>   — the actual email
      [2]  b')'
    """
    lines = response[1] if isinstance(response, tuple) else getattr(response, "lines", [])
    for line in lines:
        if isinstance(line, (bytes, bytearray)) and len(line) > 100:
            return bytes(line)
    return None


# ── Email parser ───────────────────────────────────────────────────────────────

async def find_or_create_email_thread(db, workspace_id, msg_dict):
    """
    Match an inbound email to an existing Thread or create a new one.

    Matching priority:
      1. Thread.linked_email_thread_id == In-Reply-To header
      2. Thread.linked_email_thread_id == first entry in References header
      3. Create a new Thread linked to this message's Message-ID

    Intended for use by inbox_poll._poll_account().
    """
    from app.models.thread import Thread
    from sqlalchemy import select

    in_reply_to: Optional[str] = msg_dict.get("in_reply_to")
    references: Optional[str] = msg_dict.get("references")

    # 1. Match by In-Reply-To
    if in_reply_to:
        result = await db.execute(
            select(Thread).where(
                Thread.workspace_id == workspace_id,
                Thread.linked_email_thread_id == in_reply_to,
            )
        )
        thread = result.scalar_one_or_none()
        if thread:
            return thread

    # 2. Match by first entry in References header
    if references:
        first_ref = references.split()[0]
        result = await db.execute(
            select(Thread).where(
                Thread.workspace_id == workspace_id,
                Thread.linked_email_thread_id == first_ref,
            )
        )
        thread = result.scalar_one_or_none()
        if thread:
            return thread

    # 3. New thread linked to this message's Message-ID
    subject = (msg_dict.get("subject") or "Email").strip()
    new_thread = Thread(
        workspace_id=workspace_id,
        title=subject[:512],
        linked_email_thread_id=msg_dict.get("message_id") or None,
    )
    db.add(new_thread)
    await db.flush()
    return new_thread


def _parse_raw_email(uid: int, raw: bytes) -> dict:
    """Parse raw RFC 822 bytes into a structured dict."""
    msg = email_lib.message_from_bytes(raw)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors="replace")
                break
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(charset, errors="replace")

    return {
        "uid": uid,
        "message_id": (msg.get("Message-ID") or "").strip(),
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "body": body,
        "in_reply_to": (msg.get("In-Reply-To") or "").strip() or None,
        "references": (msg.get("References") or "").strip() or None,
    }
