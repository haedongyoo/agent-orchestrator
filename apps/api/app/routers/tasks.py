from __future__ import annotations
"""
Tasks + Steps router.

Endpoints (all require Bearer JWT):
  POST  /api/threads/{thread_id}/tasks          → 201 TaskResponse
  GET   /api/tasks/{task_id}                    → 200 TaskResponse
  GET   /api/tasks/{task_id}/steps              → 200 List[TaskStepResponse]
  POST  /api/tasks/{task_id}/cancel             → 204

Flow:
  create_task → Task (queued) → Planner.decompose() → TaskStep(s) → dispatch to agent queues
  cancel_task → Task (failed) → all queued/running steps (failed)

Ownership is owner-scoped: task → thread → workspace → user_id == current_user.id.
Returns 404 (not 403) on ownership failures to avoid leaking resource existence.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.task import Task, TaskStep
from app.models.thread import Thread
from app.models.workspace import User, Workspace
from app.models.agent import Agent
from app.models.audit import AuditLog
from app.services.auth import get_current_user
from app.services.orchestrator.planner import Planner
from app.services.orchestrator.router import OrchestratorRouter

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=4096)


class TaskResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    thread_id: uuid.UUID
    objective: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskStepResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID
    step_type: str
    status: str
    tool_call: Optional[dict]
    result: Optional[dict]

    model_config = {"from_attributes": True}


class TraceStepResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    step_type: str
    status: str
    tool_call: Optional[dict]
    result: Optional[dict]
    created_at: datetime
    updated_at: datetime
    duration_ms: Optional[int]

    model_config = {"from_attributes": True}


class TraceAuditEntry(BaseModel):
    id: uuid.UUID
    actor_type: str
    actor_id: Optional[uuid.UUID]
    action: str
    target_type: Optional[str]
    target_id: Optional[uuid.UUID]
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class TraceResponse(BaseModel):
    task: TaskResponse
    steps: List[TraceStepResponse]
    audit_logs: List[TraceAuditEntry]
    total_duration_ms: Optional[int]


# ── Ownership helpers ──────────────────────────────────────────────────────────

async def _get_thread_verified(
    thread_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Thread:
    """Load a Thread and verify workspace ownership; raises 404 on any miss."""
    t = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = t.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    ws = await db.execute(
        select(Workspace).where(
            Workspace.id == thread.workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    if ws.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return thread


async def _get_task_verified(
    task_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Task:
    """Load a Task and verify workspace ownership; raises 404 on any miss."""
    t = await db.execute(select(Task).where(Task.id == task_id))
    task = t.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    ws = await db.execute(
        select(Workspace).where(
            Workspace.id == task.workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    if ws.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return task


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/threads/{thread_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    thread_id: uuid.UUID,
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """
    Create a task with an objective. The orchestrator will assign it to an agent.

    If enabled agents exist in the workspace, an initial planning step is
    created and dispatched immediately. Otherwise the task stays in 'queued'
    until an agent becomes available.
    """
    thread = await _get_thread_verified(thread_id, current_user, db)

    task = Task(
        workspace_id=thread.workspace_id,
        thread_id=thread_id,
        objective=body.objective,
        status="queued",
        created_by=current_user.id,
    )
    db.add(task)
    await db.flush()  # resolve task.id before planner

    # Find enabled agents in this workspace
    agents_result = await db.execute(
        select(Agent).where(
            Agent.workspace_id == thread.workspace_id,
            Agent.is_enabled == True,  # noqa: E712
        )
    )
    agents = agents_result.scalars().all()

    if agents:
        planner = Planner(db)
        steps = await planner.decompose(task, [a.id for a in agents])

        orch = OrchestratorRouter(db)
        for step in steps:
            await orch.enqueue_existing_step(step, workspace_id=task.workspace_id, thread_id=thread_id)

        task.status = "running"

    await db.commit()
    await db.refresh(task)
    return TaskResponse.model_validate(task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Fetch a task. Returns 404 if not found or not owned by caller."""
    task = await _get_task_verified(task_id, current_user, db)
    return TaskResponse.model_validate(task)


@router.get("/tasks/{task_id}/steps", response_model=List[TaskStepResponse])
async def list_steps(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TaskStepResponse]:
    """List all steps for a task, ordered by creation time."""
    task = await _get_task_verified(task_id, current_user, db)

    result = await db.execute(
        select(TaskStep)
        .where(TaskStep.task_id == task.id)
        .order_by(TaskStep.created_at)
    )
    steps = result.scalars().all()
    return [TaskStepResponse.model_validate(s) for s in steps]


@router.post("/tasks/{task_id}/cancel", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def cancel_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Cancel a task. Marks the task and all pending/running steps as failed.
    Already completed or failed steps are left unchanged.
    """
    task = await _get_task_verified(task_id, current_user, db)

    if task.status in ("done", "failed"):
        return  # idempotent — nothing to do

    task.status = "failed"

    # Mark all non-terminal steps as failed
    await db.execute(
        update(TaskStep)
        .where(
            TaskStep.task_id == task.id,
            TaskStep.status.in_(["queued", "running"]),
        )
        .values(status="failed")
    )

    await db.commit()


@router.get("/tasks/{task_id}/trace", response_model=TraceResponse)
async def get_task_trace(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceResponse:
    """
    Step-level execution trace for a task.

    Returns the task, all steps with agent names and durations, and
    related audit logs — ordered chronologically for debugging.
    """
    task = await _get_task_verified(task_id, current_user, db)

    # Load steps with agent names
    steps_result = await db.execute(
        select(TaskStep, Agent.name)
        .join(Agent, TaskStep.agent_id == Agent.id)
        .where(TaskStep.task_id == task.id)
        .order_by(TaskStep.created_at)
    )
    rows = steps_result.all()

    trace_steps = []
    for step, agent_name in rows:
        duration_ms = None
        if step.created_at and step.updated_at and step.status in ("done", "failed"):
            delta = step.updated_at - step.created_at
            duration_ms = int(delta.total_seconds() * 1000)

        trace_steps.append(TraceStepResponse(
            id=step.id,
            agent_id=step.agent_id,
            agent_name=agent_name,
            step_type=step.step_type,
            status=step.status,
            tool_call=step.tool_call,
            result=step.result,
            created_at=step.created_at,
            updated_at=step.updated_at,
            duration_ms=duration_ms,
        ))

    # Load related audit logs
    audit_result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.workspace_id == task.workspace_id,
            AuditLog.target_type == "task",
            AuditLog.target_id == task.id,
        )
        .order_by(AuditLog.created_at)
    )
    audit_logs = [
        TraceAuditEntry.model_validate(a)
        for a in audit_result.scalars().all()
    ]

    # Total duration from task creation to last step completion
    total_duration_ms = None
    if trace_steps and task.status in ("done", "failed"):
        last_step = trace_steps[-1]
        if last_step.updated_at and task.created_at:
            delta = last_step.updated_at - task.created_at
            total_duration_ms = int(delta.total_seconds() * 1000)

    return TraceResponse(
        task=TaskResponse.model_validate(task),
        steps=trace_steps,
        audit_logs=audit_logs,
        total_duration_ms=total_duration_ms,
    )
