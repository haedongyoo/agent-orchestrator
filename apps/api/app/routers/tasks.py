from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List
import uuid

from app.db.session import get_db

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    objective: str


class TaskResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    thread_id: uuid.UUID
    objective: str
    status: str

    class Config:
        from_attributes = True


class TaskStepResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID
    step_type: str
    status: str
    tool_call: dict | None
    result: dict | None

    class Config:
        from_attributes = True


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/threads/{thread_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(thread_id: uuid.UUID, body: TaskCreate, db: AsyncSession = Depends(get_db)):
    # Create task + enqueue initial planning step in orchestrator
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/tasks/{task_id}/steps", response_model=List[TaskStepResponse])
async def list_steps(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/tasks/{task_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")
