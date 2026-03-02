"""
Sandbox — enforces the allowed_tools list at runtime.

When the orchestrator dispatches a task step it includes the agent's
`allowed_tools` list.  This module wraps every tool call and raises
ToolNotAllowed before execution if the tool isn't in that list.

This is a defence-in-depth measure on top of network isolation:
even if an agent's prompt tries to call a forbidden tool the sandbox
will block it before any side-effect occurs.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable
import structlog

log = structlog.get_logger()


class ToolNotAllowed(Exception):
    """Raised when an agent attempts to use a tool outside its allowed list."""


class Sandbox:
    def __init__(self, allowed_tools: list[str], agent_id: str):
        self.allowed_tools = set(allowed_tools)
        self.agent_id = agent_id

    def check(self, tool_name: str) -> None:
        """Raise ToolNotAllowed if tool_name is not in the allowed set."""
        if tool_name not in self.allowed_tools:
            log.warning(
                "sandbox.tool_blocked",
                agent_id=self.agent_id,
                tool=tool_name,
                allowed=sorted(self.allowed_tools),
            )
            raise ToolNotAllowed(
                f"Agent {self.agent_id} is not allowed to use tool '{tool_name}'. "
                f"Allowed: {sorted(self.allowed_tools)}"
            )
        log.debug("sandbox.tool_allowed", agent_id=self.agent_id, tool=tool_name)

    async def call(
        self,
        tool_name: str,
        fn: Callable[..., Awaitable[Any]],
        **kwargs: Any,
    ) -> Any:
        """Check permission then execute the tool coroutine."""
        self.check(tool_name)
        return await fn(**kwargs)
