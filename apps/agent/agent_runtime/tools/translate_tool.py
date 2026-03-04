"""translate_message tool.

Translates text between languages using the LLM already available in the
agent container (LiteLLM).  Unlike other tools this executes **locally** —
no Redis round-trip or orchestrator involvement required.

Rationale:
  - No DB access, credentials, or orchestrator involvement needed.
  - The LLM is already available (same env vars as runner.py).
  - Faster than posting to the orchestrator queue.
  - Sandbox still enforces tool permissions.
"""
from __future__ import annotations

import json
import os

import structlog

log = structlog.get_logger()

LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-opus-4-6")
LLM_API_BASE = os.getenv("LLM_API_BASE")
LLM_API_KEY = os.getenv("LLM_API_KEY")

_SYSTEM_PROMPT = (
    "You are a professional translator. Translate the user's text into the "
    "requested target language. Respond ONLY with a JSON object — no markdown "
    "fences, no commentary:\n"
    '{"translated_text": "<translation>", "detected_source_language": "<language>"}\n'
    "If the source language is specified, still include it in your response."
)


async def translate_message(
    *,
    agent_id: str,
    workspace_id: str,
    thread_id: str,
    text: str,
    target_language: str,
    source_language: str = "auto",
) -> dict:
    """
    Translate *text* into *target_language* using the agent-local LLM.

    Returns dict with keys: translated_text, source_language, target_language
    On failure returns dict with key: error
    """
    log.info(
        "tool.translate_message.requested",
        agent_id=agent_id,
        target_language=target_language,
        source_language=source_language,
        text_length=len(text),
    )

    user_prompt = f"Translate the following text into {target_language}"
    if source_language != "auto":
        user_prompt += f" (source language: {source_language})"
    user_prompt += f":\n\n{text}"

    try:
        import litellm

        kwargs = dict(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4096,
        )
        if LLM_API_BASE:
            kwargs["api_base"] = LLM_API_BASE
        if LLM_API_KEY:
            kwargs["api_key"] = LLM_API_KEY

        response = await litellm.acompletion(**kwargs)
        raw = response.choices[0].message.content or ""

        # Try to parse JSON; fall back to treating raw text as translation
        try:
            parsed = json.loads(raw)
            translated = parsed.get("translated_text", raw)
            detected = parsed.get("detected_source_language", source_language)
        except (json.JSONDecodeError, TypeError):
            translated = raw.strip()
            detected = source_language

        log.info(
            "tool.translate_message.success",
            agent_id=agent_id,
            detected_source=detected,
            target_language=target_language,
        )
        return {
            "translated_text": translated,
            "source_language": detected,
            "target_language": target_language,
        }

    except Exception as exc:
        log.error("tool.translate_message.error", agent_id=agent_id, error=str(exc))
        return {"error": f"Translation failed: {exc}"}
