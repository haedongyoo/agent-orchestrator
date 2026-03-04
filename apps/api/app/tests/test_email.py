"""
Tests for the Email connector (send_email, poll_inbox, inbox_poll helpers).

All external I/O (SMTP, IMAP, DB) is mocked — no live mail server required.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.services.connectors.email import (
    OutboundEmail,
    _parse_raw_email,
    _resolve_credentials,
    _is_ok,
    _extract_uid_list,
    find_or_create_email_thread,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_creds(
    smtp_host: str = "smtp.example.com",
    smtp_port: int = 587,
    imap_host: str = "imap.example.com",
    imap_port: int = 993,
    username: str = "user@example.com",
    password: str = "s3cret",
) -> dict:
    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "imap_host": imap_host,
        "imap_port": imap_port,
        "username": username,
        "password": password,
    }


def _encrypted_creds(**kwargs) -> str:
    """Return a Fernet-encrypted JSON string suitable for credentials_ref."""
    from app.services.secrets import encrypt_api_key
    return encrypt_api_key(json.dumps(_make_creds(**kwargs)))


def _raw_email_bytes(
    from_: str = "sender@example.com",
    to: str = "recv@example.com",
    subject: str = "Hello",
    body: str = "Body text here",
    message_id: str = "<abc123@example.com>",
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> bytes:
    """Build a minimal raw RFC 822 email for testing."""
    msg = MIMEMultipart("alternative")
    msg["From"] = from_
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg.as_bytes()


# ── _resolve_credentials ───────────────────────────────────────────────────────

class TestResolveCredentials:
    def test_roundtrip_decryption(self):
        creds_ref = _encrypted_creds()
        result = _resolve_credentials(creds_ref)
        assert result["username"] == "user@example.com"
        assert result["password"] == "s3cret"
        assert result["smtp_host"] == "smtp.example.com"

    def test_invalid_token_raises(self):
        with pytest.raises(ValueError, match="decrypt"):
            _resolve_credentials("not-a-valid-fernet-token")


# ── send_email ─────────────────────────────────────────────────────────────────

class TestSendEmail:
    @pytest.mark.asyncio
    async def test_calls_aiosmtplib_send(self):
        from app.services.connectors.email import send_email

        email = OutboundEmail(
            to=["recv@example.com"],
            subject="Quote request",
            body="Please provide a quote.",
            thread_id=str(uuid.uuid4()),
        )
        creds_ref = _encrypted_creds()

        mock_aiosmtplib = MagicMock()
        mock_aiosmtplib.send = AsyncMock()

        with patch.dict("sys.modules", {"aiosmtplib": mock_aiosmtplib}):
            message_id = await send_email(email, creds_ref, from_alias="agent@example.com")

        mock_aiosmtplib.send.assert_called_once()
        assert message_id.startswith("<")
        assert "@example.com>" in message_id

    @pytest.mark.asyncio
    async def test_smtp_params_passed_correctly(self):
        from app.services.connectors.email import send_email

        email = OutboundEmail(
            to=["recv@x.com"],
            subject="S",
            body="B",
            thread_id=str(uuid.uuid4()),
        )
        creds_ref = _encrypted_creds(smtp_host="mail.custom.com", smtp_port=465)

        captured: dict = {}

        async def fake_send(msg, *, hostname, port, username, password, **kwargs):
            captured["hostname"] = hostname
            captured["port"] = port
            captured["username"] = username

        mock_aiosmtplib = MagicMock()
        mock_aiosmtplib.send = fake_send

        with patch.dict("sys.modules", {"aiosmtplib": mock_aiosmtplib}):
            await send_email(email, creds_ref, from_alias="a@x.com")

        assert captured["hostname"] == "mail.custom.com"
        assert captured["port"] == 465
        assert captured["username"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_reply_headers_set_when_provided(self):
        from app.services.connectors.email import send_email

        email = OutboundEmail(
            to=["recv@x.com"],
            subject="Re: Quote",
            body="Thanks",
            thread_id=str(uuid.uuid4()),
            reply_to_message_id="<original@example.com>",
        )
        creds_ref = _encrypted_creds()
        captured_msg = {}

        async def fake_send(msg, **kwargs):
            captured_msg["in_reply_to"] = msg.get("In-Reply-To")
            captured_msg["references"] = msg.get("References")

        mock_aiosmtplib = MagicMock()
        mock_aiosmtplib.send = fake_send

        with patch.dict("sys.modules", {"aiosmtplib": mock_aiosmtplib}):
            await send_email(email, creds_ref, from_alias="a@x.com")

        assert captured_msg["in_reply_to"] == "<original@example.com>"
        assert captured_msg["references"] == "<original@example.com>"

    @pytest.mark.asyncio
    async def test_signature_appended_to_body(self):
        from app.services.connectors.email import send_email

        email = OutboundEmail(
            to=["r@x.com"],
            subject="S",
            body="Hello",
            thread_id=str(uuid.uuid4()),
        )
        creds_ref = _encrypted_creds()
        captured_body = {}

        async def fake_send(msg, **kwargs):
            # Extract plain text part from MIME
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        captured_body["text"] = payload.decode("utf-8")

        mock_aiosmtplib = MagicMock()
        mock_aiosmtplib.send = fake_send

        with patch.dict("sys.modules", {"aiosmtplib": mock_aiosmtplib}):
            await send_email(email, creds_ref, from_alias="a@x.com", signature="-- Agent")

        assert "Hello" in captured_body["text"]
        assert "-- Agent" in captured_body["text"]


# ── _parse_raw_email ───────────────────────────────────────────────────────────

class TestParseRawEmail:
    def test_parses_basic_fields(self):
        raw = _raw_email_bytes(
            from_="sender@x.com",
            to="recv@x.com",
            subject="Test Subject",
            body="Hello world",
            message_id="<test123@x.com>",
        )
        result = _parse_raw_email(uid=42, raw=raw)

        assert result["uid"] == 42
        assert result["message_id"] == "<test123@x.com>"
        assert result["from"] == "sender@x.com"
        assert result["subject"] == "Test Subject"
        assert "Hello world" in result["body"]
        assert result["in_reply_to"] is None
        assert result["references"] is None

    def test_parses_reply_headers(self):
        raw = _raw_email_bytes(
            in_reply_to="<orig@x.com>",
            references="<orig@x.com> <prev@x.com>",
        )
        result = _parse_raw_email(uid=1, raw=raw)
        assert result["in_reply_to"] == "<orig@x.com>"
        assert result["references"] == "<orig@x.com> <prev@x.com>"

    def test_empty_reply_headers_return_none(self):
        raw = _raw_email_bytes()
        result = _parse_raw_email(uid=1, raw=raw)
        assert result["in_reply_to"] is None
        assert result["references"] is None


# ── IMAP response helpers ──────────────────────────────────────────────────────

class TestImapHelpers:
    def test_is_ok_tuple_ok(self):
        assert _is_ok(("OK", [])) is True

    def test_is_ok_tuple_no(self):
        assert _is_ok(("NO", [])) is False

    def test_is_ok_object_ok(self):
        resp = MagicMock()
        resp.result = "OK"
        assert _is_ok(resp) is True

    def test_is_ok_object_bad(self):
        resp = MagicMock()
        resp.result = "BAD"
        assert _is_ok(resp) is False

    def test_extract_uid_list_bytes(self):
        resp = ("OK", [b"1 2 3", b"Search completed"])
        uids = _extract_uid_list(resp)
        assert uids == ["1", "2", "3"]

    def test_extract_uid_list_empty(self):
        resp = ("OK", [b"", b"Search completed"])
        uids = _extract_uid_list(resp)
        assert uids == []

    def test_extract_uid_list_object(self):
        resp = MagicMock()
        resp.lines = [b"10 11 12"]
        uids = _extract_uid_list(resp)
        assert uids == ["10", "11", "12"]


# ── _find_or_create_email_thread ───────────────────────────────────────────────

class TestFindOrCreateEmailThread:
    """Test thread matching logic without live DB."""

    def _make_account(self, workspace_id=None):
        acc = MagicMock()
        acc.workspace_id = workspace_id or uuid.uuid4()
        acc.from_alias = "agent@example.com"
        return acc

    def _make_thread(self, workspace_id, linked_id):
        t = MagicMock()
        t.id = uuid.uuid4()
        t.workspace_id = workspace_id
        t.linked_email_thread_id = linked_id
        return t

    def _build_db(self, *scalar_results):
        db = AsyncMock()
        mocks = []
        for obj in scalar_results:
            m = MagicMock()
            m.scalar_one_or_none.return_value = obj
            mocks.append(m)
        db.execute = AsyncMock(side_effect=mocks)
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_matches_by_in_reply_to(self):
        ws_id = uuid.uuid4()
        existing = self._make_thread(ws_id, "<orig@x.com>")
        db = self._build_db(existing)

        msg_dict = {
            "message_id": "<new@x.com>",
            "subject": "Re: Hi",
            "in_reply_to": "<orig@x.com>",
            "references": None,
        }
        thread = await find_or_create_email_thread(db, ws_id, msg_dict)
        assert thread.id == existing.id
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_matches_by_references(self):
        ws_id = uuid.uuid4()
        existing = self._make_thread(ws_id, "<first@x.com>")
        # in_reply_to returns None, references returns existing thread
        db = self._build_db(None, existing)

        msg_dict = {
            "message_id": "<new@x.com>",
            "subject": "Reply",
            "in_reply_to": "<unknown@x.com>",
            "references": "<first@x.com> <other@x.com>",
        }
        thread = await find_or_create_email_thread(db, ws_id, msg_dict)
        assert thread.id == existing.id

    @pytest.mark.asyncio
    async def test_creates_new_thread_when_no_match(self):
        from app.models.thread import Thread

        ws_id = uuid.uuid4()
        db = self._build_db(None, None)  # both lookups return None

        msg_dict = {
            "message_id": "<brand-new@x.com>",
            "subject": "New inquiry",
            "in_reply_to": "<unknown@x.com>",
            "references": "<also-unknown@x.com>",
        }
        await find_or_create_email_thread(db, ws_id, msg_dict)
        added_threads = [
            c.args[0] for c in db.add.call_args_list
            if isinstance(c.args[0], Thread)
        ]
        assert len(added_threads) == 1
        assert added_threads[0].linked_email_thread_id == "<brand-new@x.com>"
        assert added_threads[0].title == "New inquiry"

    @pytest.mark.asyncio
    async def test_creates_new_thread_with_no_in_reply_to(self):
        from app.models.thread import Thread

        ws_id = uuid.uuid4()
        # Only one DB call when in_reply_to is None (skip that lookup)
        db = self._build_db(None)

        msg_dict = {
            "message_id": "<fresh@x.com>",
            "subject": "Fresh start",
            "in_reply_to": None,
            "references": None,
        }
        await find_or_create_email_thread(db, ws_id, msg_dict)
        added_threads = [
            c.args[0] for c in db.add.call_args_list
            if isinstance(c.args[0], Thread)
        ]
        assert len(added_threads) == 1
