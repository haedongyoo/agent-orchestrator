from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.db.session import get_db

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ThreadCreate(BaseModel):
    title: str
    workspace_id: uuid.UUID


class ThreadResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: str

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str
    channel: str = "web"


class MessageResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    sender_type: str
    channel: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(workspace_id: uuid.UUID, body: ThreadCreate, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/threads/{thread_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def post_message(thread_id: uuid.UUID, body: MessageCreate, db: AsyncSession = Depends(get_db)):
    # Persist user message, then hand off to orchestrator for agent response
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/threads/{thread_id}/messages", response_model=List[MessageResponse])
async def list_messages(
    thread_id: uuid.UUID,
    cursor: Optional[str] = Query(None, description="Pagination cursor (message ID)"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")
