"""
Tests for the Policy Engine.

Priority: HIGH — A2A enforcement is a non-negotiable safety guarantee.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.services.orchestrator.policy import PolicyEngine, RouteRequest


def make_route(**kwargs):
    defaults = dict(
        sender_type="agent",
        sender_id=uuid.uuid4(),
        receiver_type="agent",
        receiver_id=str(uuid.uuid4()),
        thread_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content_preview="hello",
    )
    defaults.update(kwargs)
    return RouteRequest(**defaults)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def engine(mock_db):
    return PolicyEngine(db=mock_db)


class TestA2APolicy:
    @pytest.mark.asyncio
    async def test_agent_to_agent_blocked_by_default(self, engine):
        req = make_route(sender_type="agent", receiver_type="agent")
        decision = await engine.check_route(req)
        assert decision.allowed is False
        assert decision.reason == "a2a_not_approved"

    @pytest.mark.asyncio
    async def test_agent_to_agent_creates_approval(self, engine, mock_db):
        req = make_route(sender_type="agent", receiver_type="agent")
        decision = await engine.check_route(req)
        assert decision.approval_id is not None
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_to_user_allowed(self, engine):
        req = make_route(sender_type="agent", receiver_type="user")
        decision = await engine.check_route(req)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_user_to_agent_allowed(self, engine):
        req = make_route(sender_type="user", receiver_type="agent")
        decision = await engine.check_route(req)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_agent_to_email_allowed_by_default(self, engine):
        req = make_route(sender_type="agent", receiver_type="external_email", receiver_id="vendor@example.com")
        decision = await engine.check_route(req)
        assert decision.allowed is True
