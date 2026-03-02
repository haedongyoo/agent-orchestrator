"""
Tests for the Orchestrator Router.

Verifies that all messages pass through policy before delivery,
and that audit logs are always written.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.orchestrator.router import OrchestratorRouter
from app.services.orchestrator.policy import PolicyDecision


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def orch(mock_db):
    return OrchestratorRouter(db=mock_db)


class TestOrchestratorRouter:
    @pytest.mark.asyncio
    async def test_blocked_route_returns_not_delivered(self, orch):
        blocked = PolicyDecision(allowed=False, reason="a2a_not_approved", approval_id=uuid.uuid4())
        with patch.object(orch.policy, "check_route", AsyncMock(return_value=blocked)):
            result = await orch.route(
                sender_type="agent",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=None,
                workspace_id=uuid.uuid4(),
                content="hello",
            )
        assert result["delivered"] is False
        assert result["blocked_by"] == "a2a_not_approved"

    @pytest.mark.asyncio
    async def test_allowed_route_writes_audit_log(self, orch, mock_db):
        allowed = PolicyDecision(allowed=True, reason="default_allow")
        with patch.object(orch.policy, "check_route", AsyncMock(return_value=allowed)):
            await orch.route(
                sender_type="user",
                sender_id=uuid.uuid4(),
                receiver_type="agent",
                receiver_id=str(uuid.uuid4()),
                thread_id=uuid.uuid4(),
                task_id=None,
                workspace_id=uuid.uuid4(),
                content="start negotiation",
            )
        mock_db.add.assert_called()
