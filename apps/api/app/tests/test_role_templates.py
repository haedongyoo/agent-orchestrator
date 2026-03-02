"""
Tests for the Role Templates endpoints.

GET /api/agent-templates       → list all 3 templates
GET /api/agent-templates/{id}  → get single template; 404 on unknown id
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.routers.role_templates import router as templates_router
from app.services.role_templates import get_template, list_templates

# Minimal test app — no DB, no auth (templates are public metadata)
app = FastAPI()
app.include_router(templates_router, prefix="/api")

KNOWN_TOOL_IDS = {
    "send_email",
    "read_email_inbox",
    "send_telegram",
    "post_web_message",
    "request_approval",
    "upsert_vendor",
    "schedule_followup",
}

EXPECTED_IDS = {"negotiator", "sourcing", "contractor"}


# ── Service layer tests ────────────────────────────────────────────────────────

class TestRoleTemplateService:
    def test_list_templates_returns_all_three(self):
        templates = list_templates()
        assert len(templates) == 3
        ids = {t.id for t in templates}
        assert ids == EXPECTED_IDS

    def test_get_negotiator(self):
        t = get_template("negotiator")
        assert t is not None
        assert t.name == "Negotiator"
        assert "negotiat" in t.role_prompt.lower()
        assert "send_email" in t.allowed_tools
        assert "request_approval" in t.allowed_tools

    def test_get_sourcing(self):
        t = get_template("sourcing")
        assert t is not None
        assert "Sourcing" in t.name
        assert "upsert_vendor" in t.allowed_tools
        assert "read_email_inbox" in t.allowed_tools

    def test_get_contractor(self):
        t = get_template("contractor")
        assert t is not None
        assert "Contractor" in t.name
        assert "send_telegram" in t.allowed_tools
        assert "request_approval" in t.allowed_tools

    def test_get_unknown_returns_none(self):
        assert get_template("unknown") is None
        assert get_template("") is None

    def test_all_template_tools_are_valid(self):
        """Every tool in every template must be in the global VALID_TOOLS allowlist."""
        for template in list_templates():
            for tool in template.allowed_tools:
                assert tool in KNOWN_TOOL_IDS, (
                    f"Template '{template.id}' references unknown tool '{tool}'"
                )

    def test_all_templates_have_non_empty_prompt(self):
        for template in list_templates():
            assert len(template.role_prompt) >= 100, (
                f"Template '{template.id}' role_prompt is too short"
            )

    def test_rate_limits_are_positive(self):
        for template in list_templates():
            assert template.rate_limit_per_min >= 1
            assert template.max_concurrency >= 1

    def test_templates_are_immutable(self):
        """Dataclass is frozen — mutation must raise."""
        t = get_template("negotiator")
        with pytest.raises((AttributeError, TypeError)):
            t.name = "Modified"  # type: ignore[misc]


# ── HTTP endpoint tests ────────────────────────────────────────────────────────

class TestListTemplatesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_all_three(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert len(data) == 3
        ids = {item["id"] for item in data}
        assert ids == EXPECTED_IDS

    @pytest.mark.asyncio
    async def test_response_schema_fields(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates")
        data = resp.json()
        for item in data:
            assert "id" in item
            assert "name" in item
            assert "description" in item
            assert "role_prompt" in item
            assert "allowed_tools" in item
            assert "rate_limit_per_min" in item
            assert "max_concurrency" in item

    @pytest.mark.asyncio
    async def test_allowed_tools_are_lists(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates")
        for item in resp.json():
            assert isinstance(item["allowed_tools"], list)
            assert len(item["allowed_tools"]) > 0


class TestGetTemplateEndpoint:
    @pytest.mark.asyncio
    async def test_get_negotiator(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates/negotiator")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["id"] == "negotiator"
        assert data["name"] == "Negotiator"
        assert len(data["role_prompt"]) >= 100

    @pytest.mark.asyncio
    async def test_get_sourcing(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates/sourcing")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["id"] == "sourcing"

    @pytest.mark.asyncio
    async def test_get_contractor(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates/contractor")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["id"] == "contractor"

    @pytest.mark.asyncio
    async def test_unknown_id_returns_404(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates/unknown")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_404_detail_message(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/agent-templates/bogus")
        assert "bogus" in resp.json()["detail"]
