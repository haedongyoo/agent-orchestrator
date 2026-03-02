"""
Tests for channel connectors (Telegram, WebChat).

Telegram tests use a minimal FastAPI app (NOT app.main) to stay Docker-free.
All DB calls are intercepted via AsyncMock — no real DB or Telegram API required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.models.agent import Agent
from app.models.thread import Thread
from app.models.workspace import Workspace
from app.services.connectors.telegram import router as telegram_router


# ── Minimal test app ───────────────────────────────────────────────────────────

app = FastAPI()
app.include_router(telegram_router, prefix="/api/connectors")


# ── Factories ──────────────────────────────────────────────────────────────────

def make_workspace(user_id: uuid.UUID | None = None) -> Workspace:
    uid = user_id or uuid.uuid4()
    return Workspace(
        id=uuid.uuid4(),
        user_id=uid,
        name="Test WS",
        timezone="UTC",
        language_pref="en",
    )


def make_agent(workspace_id: uuid.UUID) -> Agent:
    return Agent(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="Negotiator",
        role_prompt="You negotiate.",
        allowed_tools=["send_telegram"],
        telegram_bot_token_ref="123456789:ABCDefghijklmnopqrstuvwxyz",
        is_enabled=True,
        rate_limit_per_min=10,
        max_concurrency=3,
    )


def make_thread(workspace_id: uuid.UUID, chat_id: str | None = None) -> Thread:
    return Thread(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        title="Telegram conversation",
        linked_telegram_chat_id=chat_id,
    )


def _tg_update(chat_id: int = 111, text: str = "Hello agent", message_id: int = 42) -> dict:
    """Minimal Telegram Update with a text message."""
    return {
        "update_id": 99999,
        "message": {
            "message_id": message_id,
            "from": {"id": chat_id, "first_name": "Alice"},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
            "date": 1700000000,
        },
    }


def _build_db(agent, workspace, thread=None, existing_thread=None):
    """
    Build an AsyncMock db whose execute() returns the given objects in order.

    Sequence:
      1st execute: Agent lookup by ID
      2nd execute: Thread lookup (existing_thread or None)
      3rd execute: Workspace lookup for Task.created_by
    """
    db = AsyncMock()

    def make_scalar_mock(obj):
        m = MagicMock()
        m.scalar_one_or_none.return_value = obj
        return m

    def make_list_mock(objs):
        m = MagicMock()
        m.scalars.return_value.all.return_value = objs
        return m

    # Call sequence: agent, thread, workspace (+ planner flush calls)
    mocks = [
        make_scalar_mock(agent),       # Agent lookup
        make_scalar_mock(existing_thread),  # Thread lookup (None = create new)
        make_scalar_mock(workspace),   # Workspace lookup for created_by
    ]
    db.execute = AsyncMock(side_effect=mocks)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.delete = AsyncMock()
    return db


def override_db(db):
    async def _dep():
        yield db
    return _dep


# ── POST /api/connectors/telegram/{agent_id} ──────────────────────────────────

class TestTelegramWebhook:
    @pytest.mark.asyncio
    async def test_valid_message_returns_ok(self):
        ws = make_workspace()
        agent = make_agent(ws.id)

        db = _build_db(agent, ws)

        with patch("app.services.connectors.telegram.Planner") as MockPlanner, \
             patch("app.services.connectors.telegram.OrchestratorRouter") as MockOrch:
            MockPlanner.return_value.decompose = AsyncMock(return_value=[])
            MockOrch.return_value.enqueue_existing_step = MagicMock()

            app.dependency_overrides[get_db] = override_db(db)
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    resp = await c.post(
                        f"/api/connectors/telegram/{agent.id}",
                        json=_tg_update(),
                    )
                assert resp.status_code == status.HTTP_200_OK
                assert resp.json()["ok"] is True
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_agent_returns_ok(self):
        """Unknown agent → 200 ok (prevents Telegram retry loops)."""
        db = AsyncMock()
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=r)

        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/connectors/telegram/{uuid.uuid4()}",
                    json=_tg_update(),
                )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["ok"] is True
            assert resp.json()["detail"] == "agent_not_found"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_non_text_update_ignored(self):
        """Photo-only or callback updates without text are silently ignored."""
        ws = make_workspace()
        agent = make_agent(ws.id)

        db = AsyncMock()
        r = MagicMock()
        r.scalar_one_or_none.return_value = agent
        db.execute = AsyncMock(return_value=r)

        photo_update = {
            "update_id": 100,
            "message": {
                "message_id": 2,
                "chat": {"id": 111, "type": "private"},
                "photo": [{"file_id": "abc", "width": 100, "height": 100}],
            },
        }

        app.dependency_overrides[get_db] = override_db(db)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/connectors/telegram/{agent.id}",
                    json=photo_update,
                )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["ok"] is True
            assert resp.json()["detail"] == "ignored_update_type"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_existing_thread_is_reused(self):
        """If a thread for the chat_id already exists, it must be reused, not duplicated."""
        ws = make_workspace()
        agent = make_agent(ws.id)
        chat_id = "777"
        existing_thread = make_thread(ws.id, chat_id=chat_id)

        db = _build_db(agent, ws, existing_thread=existing_thread)

        with patch("app.services.connectors.telegram.Planner") as MockPlanner, \
             patch("app.services.connectors.telegram.OrchestratorRouter") as MockOrch:
            MockPlanner.return_value.decompose = AsyncMock(return_value=[])
            MockOrch.return_value.enqueue_existing_step = MagicMock()

            app.dependency_overrides[get_db] = override_db(db)
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    resp = await c.post(
                        f"/api/connectors/telegram/{agent.id}",
                        json=_tg_update(chat_id=int(chat_id)),
                    )
                assert resp.status_code == status.HTTP_200_OK
                # Thread.add should NOT have been called with a Thread object
                added_threads = [
                    call.args[0] for call in db.add.call_args_list
                    if isinstance(call.args[0], Thread)
                ]
                assert len(added_threads) == 0, "Existing thread should not be re-created"
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_new_thread_created_when_none_exists(self):
        """When no thread is linked to the chat, a new one is created."""
        ws = make_workspace()
        agent = make_agent(ws.id)

        db = _build_db(agent, ws, existing_thread=None)

        with patch("app.services.connectors.telegram.Planner") as MockPlanner, \
             patch("app.services.connectors.telegram.OrchestratorRouter") as MockOrch:
            MockPlanner.return_value.decompose = AsyncMock(return_value=[])
            MockOrch.return_value.enqueue_existing_step = MagicMock()

            app.dependency_overrides[get_db] = override_db(db)
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    resp = await c.post(
                        f"/api/connectors/telegram/{agent.id}",
                        json=_tg_update(),
                    )
                assert resp.status_code == status.HTTP_200_OK
                added_threads = [
                    call.args[0] for call in db.add.call_args_list
                    if isinstance(call.args[0], Thread)
                ]
                assert len(added_threads) == 1, "A new Thread should have been created"
                assert added_threads[0].linked_telegram_chat_id == "111"
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_task_created_and_dispatched(self):
        """Inbound message triggers Task creation and dispatch to agent queue."""
        ws = make_workspace()
        agent = make_agent(ws.id)
        fake_step = MagicMock()

        db = _build_db(agent, ws)

        with patch("app.services.connectors.telegram.Planner") as MockPlanner, \
             patch("app.services.connectors.telegram.OrchestratorRouter") as MockOrch:
            MockPlanner.return_value.decompose = AsyncMock(return_value=[fake_step])
            mock_orch = MockOrch.return_value
            mock_orch.enqueue_existing_step = MagicMock()

            app.dependency_overrides[get_db] = override_db(db)
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                    await c.post(
                        f"/api/connectors/telegram/{agent.id}",
                        json=_tg_update(text="Request a quote from supplier X"),
                    )
                MockPlanner.return_value.decompose.assert_called_once()
                mock_orch.enqueue_existing_step.assert_called_once_with(
                    fake_step, workspace_id=agent.workspace_id
                )
            finally:
                app.dependency_overrides.clear()


# ── send_message() ─────────────────────────────────────────────────────────────

class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_posts_to_telegram_api(self):
        from app.services.connectors.telegram import send_message

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 99}}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await send_message(
                bot_token="123456:ABC",
                chat_id="42",
                text="Hello from agent",
            )

        assert result["ok"] is True
        assert result["result"]["message_id"] == 99

    @pytest.mark.asyncio
    async def test_send_includes_reply_to_when_provided(self):
        from app.services.connectors.telegram import send_message

        posted_body = {}

        async def capture_post(url, json=None, **kwargs):
            posted_body.update(json or {})
            m = MagicMock()
            m.json.return_value = {"ok": True}
            m.raise_for_status = MagicMock()
            return m

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = capture_post
            await send_message(
                bot_token="tok",
                chat_id="42",
                text="Reply",
                reply_to_message_id=77,
            )

        assert posted_body.get("reply_to_message_id") == 77


# ── WebChat broadcast ──────────────────────────────────────────────────────────

class TestWebchatBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_thread_does_not_raise(self):
        from app.services.connectors.webchat import broadcast
        # No connected clients — should silently succeed
        await broadcast(uuid.uuid4(), {"type": "new_message", "content": "hi"})
