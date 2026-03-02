"""
Tests for the Policy Engine.

Priority: HIGH — A2A enforcement is a non-negotiable safety guarantee.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def _empty_execute():
    """Return a mock db.execute() that yields an empty list (no approved approvals)."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    return AsyncMock(return_value=r)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    # Default: no existing approved approvals in the DB
    db.execute = _empty_execute()
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
        req = make_route(
            sender_type="agent",
            receiver_type="external_email",
            receiver_id="vendor@example.com",
        )
        decision = await engine.check_route(req)
        assert decision.allowed is True


class TestA2AApprovedScope:
    """A2A is allowed when a valid approved Approval row matches the route scope."""

    def _make_approval(self, sender_id, receiver_id, thread_id, **scope_extra):
        from app.models.approval import Approval

        approval = Approval(
            id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            approval_type="enable_agent_chat",
            requested_by=sender_id,
            scope={
                "agents": [str(sender_id), str(receiver_id)],
                "thread_id": str(thread_id),
                **scope_extra,
            },
            status="approved",
        )
        approval.decided_at = datetime.now(timezone.utc)
        return approval

    def _db_with_approval(self, approval, mock_db):
        r = MagicMock()
        r.scalars.return_value.all.return_value = [approval]
        mock_db.execute = AsyncMock(return_value=r)
        return mock_db

    @pytest.mark.asyncio
    async def test_agent_to_agent_allowed_with_active_approval(self, mock_db):
        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        approval = self._make_approval(sender_id, receiver_id, thread_id)
        approval.workspace_id = workspace_id

        db = self._db_with_approval(approval, mock_db)
        engine = PolicyEngine(db=db)

        req = make_route(
            sender_type="agent",
            sender_id=sender_id,
            receiver_type="agent",
            receiver_id=str(receiver_id),
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        decision = await engine.check_route(req)
        assert decision.allowed is True
        assert decision.reason == "a2a_approved"

    @pytest.mark.asyncio
    async def test_expired_approval_still_blocks(self, mock_db):
        """An approval whose duration_seconds has elapsed should be treated as expired."""
        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        approval = self._make_approval(
            sender_id, receiver_id, thread_id, duration_seconds=60
        )
        # decided_at was 2 minutes ago → expired
        approval.decided_at = datetime.now(timezone.utc) - timedelta(minutes=2)

        db = self._db_with_approval(approval, mock_db)
        engine = PolicyEngine(db=db)

        req = make_route(
            sender_type="agent",
            sender_id=sender_id,
            receiver_type="agent",
            receiver_id=str(receiver_id),
            thread_id=thread_id,
        )
        decision = await engine.check_route(req)
        assert decision.allowed is False
        assert decision.reason == "a2a_not_approved"

    @pytest.mark.asyncio
    async def test_approval_wrong_thread_blocks(self, mock_db):
        """An approval scoped to a different thread must not grant access."""
        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        approval = self._make_approval(sender_id, receiver_id, uuid.uuid4())  # different thread

        db = self._db_with_approval(approval, mock_db)
        engine = PolicyEngine(db=db)

        req = make_route(
            sender_type="agent",
            sender_id=sender_id,
            receiver_type="agent",
            receiver_id=str(receiver_id),
            thread_id=thread_id,
        )
        decision = await engine.check_route(req)
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_approval_wrong_agent_pair_blocks(self, mock_db):
        """An approval for a different agent pair must not grant access."""
        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        # Approval is for a completely different pair
        approval = self._make_approval(uuid.uuid4(), uuid.uuid4(), thread_id)

        db = self._db_with_approval(approval, mock_db)
        engine = PolicyEngine(db=db)

        req = make_route(
            sender_type="agent",
            sender_id=sender_id,
            receiver_type="agent",
            receiver_id=str(receiver_id),
            thread_id=thread_id,
        )
        decision = await engine.check_route(req)
        assert decision.allowed is False
