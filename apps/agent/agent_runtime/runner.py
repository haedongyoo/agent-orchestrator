"""
Agent Runner — executes a single task step via LiteLLM (provider-agnostic).

LiteLLM translates a single OpenAI-compatible interface to 100+ LLM providers.
Switch provider by setting env vars — no code changes required:

    LLM_MODEL=anthropic/claude-opus-4-6   LLM_API_KEY=sk-ant-...
    LLM_MODEL=gpt-4o                       LLM_API_KEY=sk-...
    LLM_MODEL=gemini/gemini-1.5-pro        LLM_API_KEY=AIza...
    LLM_MODEL=ollama/llama3.3              LLM_API_BASE=http://ollama:11434
    LLM_MODEL=groq/llama-3.3-70b-versatile LLM_API_KEY=gsk_...

Rate limiting:
  _create_with_retry() catches RateLimitError (429) and ServiceUnavailableError
  (503/529), reads the retry-after header, and sleeps until the window resets.
  No cap on retry attempts — only a ceiling on total accumulated wait time.

The runner has NO direct access to Postgres or the internal API.
All I/O goes through the sandbox tools (email/Telegram/Redis).
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

import litellm
import litellm.exceptions
import structlog

from agent_runtime.sandbox import Sandbox
from agent_runtime.tools import build_tool_registry, TOOL_SCHEMAS

log = structlog.get_logger()

# ── LLM config (all from env vars) ────────────────────────────────────────────
# Model string — provider prefix tells LiteLLM which backend to use.
# Examples: "anthropic/claude-opus-4-6", "gpt-4o", "ollama/llama3.3"
LLM_MODEL    = os.getenv("LLM_MODEL",      "anthropic/claude-opus-4-6")
LLM_API_BASE = os.getenv("LLM_API_BASE")   # required for Ollama / Azure custom endpoint
LLM_API_KEY  = os.getenv("LLM_API_KEY")    # provider API key (LiteLLM also reads OPENAI_API_KEY etc.)
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# ── Rate-limit retry config ────────────────────────────────────────────────────
DEFAULT_RETRY_AFTER  = 60    # seconds to wait when retry-after header is absent
MAX_RATE_LIMIT_WAIT  = 7200  # 2-hour ceiling on total accumulated wait (safety valve)

# Disable LiteLLM's own telemetry and verbose logging — we use structlog
litellm.telemetry = False
litellm.set_verbose = False


@dataclass
class TaskStepPayload:
    """Serialisable payload dispatched from the orchestrator."""
    step_id: str
    task_id: str
    agent_id: str
    workspace_id: str
    thread_id: str
    role_prompt: str
    allowed_tools: list[str]
    thread_history: list[dict]   # prior messages in OpenAI message format
    tool_call: dict | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class StepResult:
    step_id: str
    task_id: str
    agent_id: str
    success: bool
    output: dict
    error: str | None = None


class AgentRunner:
    def __init__(self):
        self.model      = LLM_MODEL
        self.api_base   = LLM_API_BASE or None
        self.api_key    = LLM_API_KEY  or None
        self.max_tokens = LLM_MAX_TOKENS

    async def run(self, payload: TaskStepPayload) -> StepResult:
        sandbox = Sandbox(
            allowed_tools=payload.allowed_tools,
            agent_id=payload.agent_id,
        )
        tool_registry = build_tool_registry(
            sandbox=sandbox,
            agent_id=payload.agent_id,
            workspace_id=payload.workspace_id,
            thread_id=payload.thread_id,
        )

        # Only expose schemas for tools this agent is allowed to use
        active_schemas = [
            s for s in TOOL_SCHEMAS if s["function"]["name"] in payload.allowed_tools
        ]

        log.info(
            "agent.run_start",
            step_id=payload.step_id,
            agent_id=payload.agent_id,
            model=self.model,
            tools=payload.allowed_tools,
        )

        try:
            output = await self._agentic_loop(
                system=payload.role_prompt,
                history=list(payload.thread_history),
                tools=active_schemas,
                tool_registry=tool_registry,
            )
            return StepResult(
                step_id=payload.step_id,
                task_id=payload.task_id,
                agent_id=payload.agent_id,
                success=True,
                output=output,
            )
        except Exception as exc:
            log.error("agent.run_error", step_id=payload.step_id, error=str(exc))
            return StepResult(
                step_id=payload.step_id,
                task_id=payload.task_id,
                agent_id=payload.agent_id,
                success=False,
                output={},
                error=str(exc),
            )

    # ── Agentic loop ───────────────────────────────────────────────────────────

    async def _agentic_loop(
        self,
        system: str,
        history: list[dict],
        tools: list[dict],
        tool_registry: dict,
        max_iterations: int = 10,
    ) -> dict:
        """
        Run the tool-use loop in OpenAI message format (LiteLLM universal format).

        Messages structure:
          [system] → [user/assistant turns from history] → [assistant + tool loop]
        """
        messages: list[dict] = [{"role": "system", "content": system}, *history]

        for iteration in range(max_iterations):
            response = await self._create_with_retry(
                messages=messages,
                tools=tools or None,
            )

            choice     = response.choices[0]
            message    = choice.message
            finish     = choice.finish_reason  # "stop" | "tool_calls" | "length"

            # Append assistant turn (preserves tool_calls for conversation continuity)
            messages.append(_assistant_message(message))

            # Done — model finished without requesting a tool
            if finish == "stop" or not message.tool_calls:
                return {
                    "text": message.content or "",
                    "iterations": iteration + 1,
                    "model": self.model,
                }

            # Process all tool calls in this turn
            tool_results = []
            for tc in message.tool_calls:
                tool_name  = tc.function.name
                tool_input = _parse_arguments(tc.function.arguments)

                result = await self._dispatch_tool(tool_name, tool_input, tool_registry)

                log.debug(
                    "agent.tool_call",
                    tool=tool_name,
                    success="error" not in result,
                )

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

            messages.extend(tool_results)

        return {
            "text": "",
            "iterations": max_iterations,
            "truncated": True,
            "model": self.model,
        }

    # ── Rate-limit-aware API wrapper ───────────────────────────────────────────

    async def _create_with_retry(self, messages: list[dict], tools: list[dict] | None) -> Any:
        """
        Call litellm.acompletion() and retry on rate limit / overload errors.

        Handles:
          - litellm.exceptions.RateLimitError (HTTP 429)
          - litellm.exceptions.ServiceUnavailableError (HTTP 503 / 529)

        Waits exactly as long as the retry-after header instructs, then retries
        the same call transparently. Raises only if total wait exceeds MAX_RATE_LIMIT_WAIT.
        """
        total_waited = 0.0
        attempt      = 0

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
        )
        if tools:
            kwargs["tools"]       = tools
            kwargs["tool_choice"] = "auto"
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key

        while True:
            try:
                return await litellm.acompletion(**kwargs)

            except litellm.exceptions.RateLimitError as exc:
                wait = _parse_retry_after(exc)
                total_waited, attempt = await self._wait_and_retry(
                    exc, wait, total_waited, attempt, reason="rate_limit_429"
                )

            except litellm.exceptions.ServiceUnavailableError as exc:
                wait = _parse_retry_after(exc)
                total_waited, attempt = await self._wait_and_retry(
                    exc, wait, total_waited, attempt, reason="service_unavailable"
                )

    async def _wait_and_retry(
        self,
        exc: Exception,
        wait: float,
        total_waited: float,
        attempt: int,
        reason: str,
    ) -> tuple[float, int]:
        """Log, enforce ceiling, sleep, return updated counters."""
        if total_waited + wait > MAX_RATE_LIMIT_WAIT:
            log.error(
                "agent.rate_limit.ceiling_reached",
                reason=reason,
                total_waited_seconds=total_waited,
                would_wait_seconds=wait,
                ceiling_seconds=MAX_RATE_LIMIT_WAIT,
            )
            raise exc

        attempt      += 1
        total_waited += wait

        log.warning(
            "agent.rate_limit.waiting",
            reason=reason,
            model=self.model,
            attempt=attempt,
            wait_seconds=wait,
            total_waited_seconds=total_waited,
            **_quota_headers(exc),
        )

        await asyncio.sleep(wait)
        log.info("agent.rate_limit.resuming", attempt=attempt, model=self.model)

        return total_waited, attempt

    # ── Tool dispatch ──────────────────────────────────────────────────────────

    async def _dispatch_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_registry: dict,
    ) -> Any:
        fn = tool_registry.get(tool_name)
        if fn is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await fn(**tool_input)
        except Exception as exc:
            return {"error": str(exc)}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _assistant_message(message: Any) -> dict:
    """
    Convert a LiteLLM/OpenAI message object to a plain dict safe for
    re-sending in the next messages list.
    """
    msg: dict[str, Any] = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id":       tc.id,
                "type":     "function",
                "function": {
                    "name":      tc.function.name,
                    "arguments": tc.function.arguments,  # already a JSON string
                },
            }
            for tc in message.tool_calls
        ]
    return msg


def _parse_arguments(arguments: str) -> dict:
    """Safely parse a JSON string of tool arguments."""
    try:
        return json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_retry_after(exc: Exception) -> float:
    """Extract retry-after seconds from the exception's response headers."""
    try:
        raw = exc.response.headers.get("retry-after", "")  # type: ignore[attr-defined]
        if raw:
            return max(1.0, float(raw))
    except (AttributeError, ValueError, TypeError):
        pass
    return float(DEFAULT_RETRY_AFTER)


def _quota_headers(exc: Exception) -> dict:
    """Pull rate-limit quota headers for structured log output."""
    try:
        h = exc.response.headers  # type: ignore[attr-defined]
        return {
            "remaining_requests": h.get("x-ratelimit-remaining-requests"),
            "remaining_tokens":   h.get("x-ratelimit-remaining-tokens"),
            "reset_requests":     h.get("x-ratelimit-reset-requests"),
            "reset_tokens":       h.get("x-ratelimit-reset-tokens"),
        }
    except AttributeError:
        return {}
