"""
Tests for channel connectors (Telegram, Email, WebChat).
"""
import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTelegramConnector:
    def test_webhook_returns_ok(self, client):
        payload = {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "chat": {"id": 456, "type": "private"},
                "text": "hello",
            },
        }
        resp = client.post("/api/connectors/telegram/abc123hash", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestWebchatBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_thread_does_not_raise(self):
        from app.services.connectors.webchat import broadcast
        # No connected clients — should silently succeed
        await broadcast(uuid.uuid4(), {"type": "new_message", "content": "hi"})
