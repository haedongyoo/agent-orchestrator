"""
Planner — decomposes a task objective into executable steps.

Given a task objective (e.g. "Contact furniture suppliers, request quotes"),
the planner produces an ordered list of TaskStep records and enqueues them.
"""
from __future__ import annotations

import uuid
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStep


class Planner:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def decompose(self, task: Task, available_agent_ids: List[uuid.UUID]) -> List[TaskStep]:
        """
        Produce initial plan steps for a task.

        MVP approach: single planning step assigned to the first available agent.
        V1: call OpenClaw with the task objective + agent roster to get a structured plan.
        """
        if not available_agent_ids:
            raise ValueError("No enabled agents available in workspace")

        # TODO: replace with real LLM-based decomposition
        step = TaskStep(
            task_id=task.id,
            agent_id=available_agent_ids[0],
            step_type="plan",
            tool_call=None,
            status="queued",
        )
        self.db.add(step)
        await self.db.flush()
        return [step]
