"""
Tests for the translate_message agent tool.

All tests mock litellm.acompletion to avoid real LLM calls.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Add apps/agent to sys.path so agent_runtime is importable ────────────────
_AGENT_ROOT = str(Path(__file__).resolve().parents[3] / "agent")
if _AGENT_ROOT not in sys.path:
    sys.path.insert(0, _AGENT_ROOT)

# ── Stub litellm so the tool module can be imported without the real package ──
_litellm_stub = types.ModuleType("litellm")
_litellm_stub.acompletion = AsyncMock()
_litellm_exc = types.ModuleType("litellm.exceptions")
_litellm_stub.exceptions = _litellm_exc
sys.modules.setdefault("litellm", _litellm_stub)
sys.modules.setdefault("litellm.exceptions", _litellm_exc)

# Stub structlog (agent code imports it; not in API requirements)
_structlog_stub = types.ModuleType("structlog")
_structlog_stub.get_logger = lambda: MagicMock()
sys.modules.setdefault("structlog", _structlog_stub)

from agent_runtime.tools.translate_tool import translate_message  # noqa: E402

# Common kwargs passed by the sandbox wrapper
_CTX = dict(agent_id="a1", workspace_id="w1", thread_id="t1")


def _mock_response(content: str):
    """Build a minimal LiteLLM-style response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestTranslateMessageTool:
    @pytest.mark.asyncio
    async def test_successful_json_translation(self):
        """LLM returns well-formed JSON → parsed correctly."""
        llm_json = json.dumps({
            "translated_text": "Hola mundo",
            "detected_source_language": "English",
        })
        mock_acomp = AsyncMock(return_value=_mock_response(llm_json))
        with patch.object(_litellm_stub, "acompletion", mock_acomp):
            result = await translate_message(
                **_CTX, text="Hello world", target_language="Spanish",
            )

        assert result["translated_text"] == "Hola mundo"
        assert result["source_language"] == "English"
        assert result["target_language"] == "Spanish"

    @pytest.mark.asyncio
    async def test_plain_text_fallback(self):
        """LLM returns plain text instead of JSON → still works."""
        mock_acomp = AsyncMock(return_value=_mock_response("Hola mundo"))
        with patch.object(_litellm_stub, "acompletion", mock_acomp):
            result = await translate_message(
                **_CTX, text="Hello world", target_language="Spanish",
            )

        assert result["translated_text"] == "Hola mundo"
        assert result["target_language"] == "Spanish"

    @pytest.mark.asyncio
    async def test_explicit_source_language_forwarded(self):
        """When source_language is explicit, it appears in the prompt."""
        llm_json = json.dumps({
            "translated_text": "Bonjour",
            "detected_source_language": "English",
        })
        mock_acomp = AsyncMock(return_value=_mock_response(llm_json))
        with patch.object(_litellm_stub, "acompletion", mock_acomp):
            result = await translate_message(
                **_CTX,
                text="Hello",
                target_language="French",
                source_language="English",
            )

            # Verify source language was included in the user prompt
            call_kwargs = mock_acomp.call_args[1]
            user_msg = call_kwargs["messages"][1]["content"]
            assert "source language: English" in user_msg

        assert result["translated_text"] == "Bonjour"
        assert result["source_language"] == "English"

    @pytest.mark.asyncio
    async def test_auto_source_language_omitted_from_prompt(self):
        """When source_language is 'auto', 'source language:' is NOT in the prompt."""
        llm_json = json.dumps({
            "translated_text": "Hallo",
            "detected_source_language": "English",
        })
        mock_acomp = AsyncMock(return_value=_mock_response(llm_json))
        with patch.object(_litellm_stub, "acompletion", mock_acomp):
            await translate_message(
                **_CTX, text="Hello", target_language="German",
            )

            call_kwargs = mock_acomp.call_args[1]
            user_msg = call_kwargs["messages"][1]["content"]
            assert "source language:" not in user_msg

    @pytest.mark.asyncio
    async def test_llm_error_returns_error_dict(self):
        """LLM raises an exception → returns error dict, no exception propagated."""
        mock_acomp = AsyncMock(side_effect=RuntimeError("LLM down"))
        with patch.object(_litellm_stub, "acompletion", mock_acomp):
            result = await translate_message(
                **_CTX, text="Hello", target_language="Japanese",
            )

        assert "error" in result
        assert "LLM down" in result["error"]

    @pytest.mark.asyncio
    async def test_max_tokens_is_4096(self):
        """Translation calls should use max_tokens=4096, not the runner's 32K."""
        llm_json = json.dumps({
            "translated_text": "Ciao",
            "detected_source_language": "English",
        })
        mock_acomp = AsyncMock(return_value=_mock_response(llm_json))
        with patch.object(_litellm_stub, "acompletion", mock_acomp):
            await translate_message(
                **_CTX, text="Hello", target_language="Italian",
            )
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["max_tokens"] == 4096


class TestTranslateMessageInValidTools:
    def test_translate_message_in_valid_tools(self):
        """translate_message must be in the API's VALID_TOOLS allowlist."""
        from app.routers.agents import VALID_TOOLS
        assert "translate_message" in VALID_TOOLS
