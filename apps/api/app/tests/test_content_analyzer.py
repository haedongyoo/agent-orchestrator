"""
Tests for ContentAnalyzer and Policy Engine content/domain checks.

All DB calls intercepted via AsyncMock — no real DB needed.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.orchestrator.content_analyzer import ContentAnalyzer, ContentAnalysis
from app.services.orchestrator.policy import PolicyEngine, RouteRequest, PolicyDecision


# ── Content Analyzer Unit Tests ──────────────────────────────────────────────

class TestContentAnalyzer:
    """Tests for regex-based content analysis."""

    def setup_method(self):
        self.analyzer = ContentAnalyzer()

    def test_empty_content(self):
        result = self.analyzer.analyze("")
        assert result.risk_level == "none"
        assert result.detected_patterns == []

    def test_normal_conversation_no_false_positives(self):
        texts = [
            "Can you check the inventory status?",
            "Please send the product catalog to the customer.",
            "What time is the meeting tomorrow?",
            "I need a status update on the order.",
            "The shipment has been dispatched.",
        ]
        for text in texts:
            result = self.analyzer.analyze(text)
            assert result.risk_level == "none", f"False positive on: {text}"

    def test_commitment_language_detected(self):
        texts = [
            "I agree to the terms of this deal.",
            "We confirm acceptance of the contract terms.",
            "Let me finalize the agreement with the vendor.",
            "I accept the offer from supplier A.",
            "We commit to the deal at the proposed price.",
        ]
        for text in texts:
            result = self.analyzer.analyze(text)
            assert result.has_commitment, f"Missed commitment: {text}"
            assert result.risk_level == "high"

    def test_payment_language_detected(self):
        texts = [
            "Please process the payment of $5,000.",
            "Send the wire transfer to the account.",
            "The invoice total is $12,500.00",
            "We need to remit the deposit.",
            "Payment of 10,000 USD is due.",
        ]
        for text in texts:
            result = self.analyzer.analyze(text)
            assert result.has_payment, f"Missed payment: {text}"
            assert result.risk_level == "high"

    def test_scope_change_detected(self):
        texts = [
            "We need to change the scope of the project.",
            "Let's modify the timeline for delivery.",
            "I want to amend the specifications.",
            "We should revise the deliverables list.",
        ]
        for text in texts:
            result = self.analyzer.analyze(text)
            assert result.has_scope_change, f"Missed scope change: {text}"
            assert result.risk_level == "low"

    def test_timeline_change_detected(self):
        texts = [
            "Can we extend the deadline by two weeks?",
            "Let's postpone the delivery date.",
        ]
        for text in texts:
            result = self.analyzer.analyze(text)
            assert result.has_scope_change, f"Missed timeline change: {text}"

    def test_combined_commitment_and_payment(self):
        text = "I agree to the contract terms and will wire $50,000 as deposit."
        result = self.analyzer.analyze(text)
        assert result.has_commitment
        assert result.has_payment
        assert result.risk_level == "high"
        assert len(result.detected_patterns) >= 2

    def test_dollar_amount_pattern(self):
        result = self.analyzer.analyze("The price is $1,234.56")
        assert result.has_payment
        assert "dollar amount" in result.detected_patterns

    def test_legal_language(self):
        result = self.analyzer.analyze("This is hereby confirmed as binding.")
        assert result.has_commitment
        assert "legal language" in result.detected_patterns

    def test_patterns_deduplicated(self):
        text = "payment payment payment invoice invoice"
        result = self.analyzer.analyze(text)
        # Should not have duplicate "payment terms" entries
        assert len(result.detected_patterns) == len(set(result.detected_patterns))

    def test_banking_details(self):
        result = self.analyzer.analyze("Send to bank account number 12345")
        assert result.has_payment
        assert "banking details" in result.detected_patterns


# ── Policy Engine Content Check Tests ────────────────────────────────────────

class TestPolicyContentCheck:
    """Tests for PolicyEngine._check_content()."""

    def _make_req(self, sender_type: str = "agent", content: str = "Hello") -> RouteRequest:
        return RouteRequest(
            sender_type=sender_type,
            sender_id=uuid.uuid4(),
            receiver_type="external_email",
            receiver_id="buyer@example.com",
            thread_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            content_preview=content[:200],
        )

    @pytest.mark.asyncio
    async def test_agent_commitment_blocked(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        engine = PolicyEngine(db)

        # Also need to mock _check_email_recipient to return allowed
        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("agent", "I agree to the contract terms for this deal.")
            decision = await engine.check_route(req)

        assert not decision.allowed
        assert "content_blocked" in decision.reason
        assert decision.approval_id is not None
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_payment_blocked(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        engine = PolicyEngine(db)

        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("agent", "Please send payment of $5,000 to account.")
            decision = await engine.check_route(req)

        assert not decision.allowed
        assert decision.approval_id is not None

    @pytest.mark.asyncio
    async def test_user_commitment_not_blocked(self):
        """Users are trusted — content scanning only applies to agents."""
        db = AsyncMock()
        engine = PolicyEngine(db)

        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("user", "I agree to the contract terms for this deal.")
            decision = await engine.check_route(req)

        assert decision.allowed

    @pytest.mark.asyncio
    async def test_agent_normal_content_allowed(self):
        db = AsyncMock()
        engine = PolicyEngine(db)

        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("agent", "Here is the product catalog you requested.")
            decision = await engine.check_route(req)

        assert decision.allowed

    @pytest.mark.asyncio
    async def test_scope_change_blocked(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        engine = PolicyEngine(db)

        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("agent", "We should change the scope of the deliverables.")
            decision = await engine.check_route(req)

        assert not decision.allowed
        assert "content_blocked_low" in decision.reason

    @pytest.mark.asyncio
    async def test_commitment_creates_correct_approval_type(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        engine = PolicyEngine(db)

        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("agent", "I confirm acceptance of the contract terms.")
            await engine.check_route(req)

        added = db.add.call_args[0][0]
        assert added.approval_type == "commitment_detected"

    @pytest.mark.asyncio
    async def test_payment_creates_correct_approval_type(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        engine = PolicyEngine(db)

        with patch.object(engine, "_check_email_recipient", return_value=PolicyDecision(allowed=True, reason="ok")):
            req = self._make_req("agent", "Payment of $10,000 is due next week.")
            await engine.check_route(req)

        added = db.add.call_args[0][0]
        assert added.approval_type == "payment_detected"


# ── Policy Engine Email Domain Check Tests ───────────────────────────────────

class TestPolicyEmailDomain:
    """Tests for PolicyEngine._check_email_recipient() with domain allowlist."""

    def _make_email_req(self, recipient: str = "buyer@example.com", workspace_id=None) -> RouteRequest:
        return RouteRequest(
            sender_type="agent",
            sender_id=uuid.uuid4(),
            receiver_type="external_email",
            receiver_id=recipient,
            thread_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            workspace_id=workspace_id or uuid.uuid4(),
            content_preview="Hello",
        )

    @pytest.mark.asyncio
    async def test_no_allowlist_allows_all(self):
        """When allowed_email_domains is None, all domains pass."""
        ws = MagicMock()
        ws.allowed_email_domains = None

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ws
        db.execute.return_value = mock_result

        engine = PolicyEngine(db)
        req = self._make_email_req("anyone@anywhere.com")
        decision = await engine._check_email_recipient(req)

        assert decision.allowed

    @pytest.mark.asyncio
    async def test_allowed_domain_passes(self):
        ws = MagicMock()
        ws.allowed_email_domains = ["example.com", "acme.org"]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ws
        db.execute.return_value = mock_result

        engine = PolicyEngine(db)
        req = self._make_email_req("buyer@example.com")
        decision = await engine._check_email_recipient(req)

        assert decision.allowed
        assert decision.reason == "email_domain_allowed"

    @pytest.mark.asyncio
    async def test_blocked_domain_creates_approval(self):
        ws = MagicMock()
        ws.allowed_email_domains = ["example.com"]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ws
        db.execute.return_value = mock_result
        db.add = MagicMock()
        db.flush = AsyncMock()

        engine = PolicyEngine(db)
        req = self._make_email_req("buyer@blocked.com")
        decision = await engine._check_email_recipient(req)

        assert not decision.allowed
        assert decision.reason == "email_domain_not_allowed"
        assert decision.approval_id is not None

        # Verify approval was created with correct type
        added = db.add.call_args[0][0]
        assert added.approval_type == "new_recipient"

    @pytest.mark.asyncio
    async def test_domain_check_case_insensitive(self):
        ws = MagicMock()
        ws.allowed_email_domains = ["Example.COM"]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ws
        db.execute.return_value = mock_result

        engine = PolicyEngine(db)
        req = self._make_email_req("buyer@example.com")
        decision = await engine._check_email_recipient(req)

        assert decision.allowed

    @pytest.mark.asyncio
    async def test_empty_allowlist_allows_all(self):
        ws = MagicMock()
        ws.allowed_email_domains = []

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ws
        db.execute.return_value = mock_result

        engine = PolicyEngine(db)
        req = self._make_email_req("buyer@anywhere.com")
        decision = await engine._check_email_recipient(req)

        assert decision.allowed


# ── Approval Types Test ──────────────────────────────────────────────────────

class TestApprovalTypes:
    """Verify new approval types are registered."""

    def test_new_types_in_approval_types(self):
        from app.models.approval import APPROVAL_TYPES

        assert "commitment_detected" in APPROVAL_TYPES
        assert "payment_detected" in APPROVAL_TYPES
        assert "scope_change_detected" in APPROVAL_TYPES


# ── Approval Tool Test ───────────────────────────────────────────────────────

class TestApprovalTool:
    """Tests for agent request_approval tool wiring."""

    @pytest.mark.asyncio
    async def test_request_approval_posts_to_queue(self):
        import sys
        import os
        # tests/ → app/ → api/ → apps/ then into agent/
        _AGENT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "agent"))
        if _AGENT_DIR not in sys.path:
            sys.path.insert(0, _AGENT_DIR)

        # Pre-create a mock celery module so the tool's lazy import works
        mock_celery_module = MagicMock()
        mock_celery_app = MagicMock()
        mock_celery_app.send_task = MagicMock()
        mock_celery_module.current_app = mock_celery_app

        # Remove cached module if already imported
        for key in list(sys.modules.keys()):
            if key.startswith("agent_runtime.tools.approval_tool"):
                del sys.modules[key]

        sys.modules["celery"] = mock_celery_module

        try:
            from agent_runtime.tools.approval_tool import request_approval

            result = await request_approval(
                agent_id=str(uuid.uuid4()),
                workspace_id=str(uuid.uuid4()),
                thread_id=str(uuid.uuid4()),
                approval_type="send_email",
                scope={"recipients": ["buyer@example.com"]},
                reason="Agent wants to send email to new recipient",
            )

            assert result["status"] == "pending"
            mock_celery_app.send_task.assert_called_once()
            call_args = mock_celery_app.send_task.call_args
            assert call_args[0][0] == "app.tasks.approval_handler.handle_approval_request"
            assert call_args[1]["queue"] == "orchestrator"
        finally:
            # Restore celery module
            del sys.modules["celery"]


# ── Approval Handler Test ────────────────────────────────────────────────────

class TestApprovalHandler:
    """Tests for the orchestrator-side approval handler task."""

    @pytest.mark.asyncio
    async def test_handle_creates_approval(self):
        from app.tasks.approval_handler import _handle

        agent_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        # No active task found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("app.db.session.AsyncSessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _handle(
                agent_id=agent_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                approval_type="send_email",
                scope={"recipients": ["buyer@example.com"]},
                reason="Testing",
            )

        assert result["status"] == "pending"
        assert "approval_id" in result
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
