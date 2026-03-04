from __future__ import annotations
"""
Threads + Messages router.

Endpoints (all require Bearer JWT):
  POST  /api/workspaces/{id}/threads              → 201 ThreadResponse
  GET   /api/threads/{threadId}                   → 200 ThreadResponse
  POST  /api/threads/{threadId}/messages          → 201 MessageResponse
  GET   /api/threads/{threadId}/messages          → 200 MessagePage (cursor-paginated)

Cursor pagination:
  Cursor = base64url(JSON{"created_at": iso, "id": str})
  Sorted ascending by (created_at, id) — stable even with sub-millisecond inserts.
  When len(items) == limit → next_cursor is set.
  When len(items) < limit  → next_cursor is None (end of results).

Security:
  Thread access is owner-scoped: thread → workspace → user_id == current_user.id.
  Returns 404 (not 403) on ownership failures to avoid leaking resource existence.
"""
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.message import Message
from app.models.thread import Thread
from app.models.workspace import User, Workspace
from app.services.auth import get_current_user

router = APIRouter()

_VALID_CHANNELS = frozenset({"web", "telegram", "email", "system"})


# ── Schemas ────────────────────────────────────────────────────────────────────

class ThreadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class ThreadResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: str

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    channel: str = Field(default="web")

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in _VALID_CHANNELS:
            raise ValueError(f"Invalid channel '{v}'. Must be one of: {sorted(_VALID_CHANNELS)}")
        return v


class MessageResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    sender_type: str
    sender_id: Optional[uuid.UUID]
    channel: str
    content: str
    created_at: str  # ISO 8601

    model_config = {"from_attributes": True}


class MessagePage(BaseModel):
    items: List[MessageResponse]
    next_cursor: Optional[str]  # None when no more pages


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_owned_workspace_by_id(
    workspace_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


async def _get_thread_with_ownership(
    thread_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Thread:
    """
    Load thread by id, then verify the workspace belongs to current_user.
    Returns 404 on either miss to avoid leaking existence.
    """
    # Load thread first
    t_result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = t_result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    # Verify workspace ownership
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == thread.workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    if ws_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return thread


def _make_cursor(msg: Message) -> str:
    payload = json.dumps({
        "created_at": msg.created_at.isoformat(),
        "id": str(msg.id),
    }).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=="
        raw = base64.urlsafe_b64decode(padded)
        data = json.loads(raw)
        dt = datetime.fromisoformat(data["created_at"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt, uuid.UUID(data["id"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid cursor",
        )


def _msg_to_response(msg: Message) -> MessageResponse:
    return MessageResponse(
        id=msg.id,
        thread_id=msg.thread_id,
        sender_type=msg.sender_type,
        sender_id=msg.sender_id,
        channel=msg.channel,
        content=msg.content,
        created_at=msg.created_at.isoformat(),
    )


# ── Thread endpoints ───────────────────────────────────────────────────────────

@router.post(
    "/workspaces/{workspace_id}/threads",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    workspace_id: uuid.UUID,
    body: ThreadCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Create a new thread in the workspace."""
    await _get_owned_workspace_by_id(workspace_id, current_user, db)

    thread = Thread(
        workspace_id=workspace_id,
        title=body.title,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return ThreadResponse.model_validate(thread)


@router.get(
    "/workspaces/{workspace_id}/threads",
    response_model=list[ThreadResponse],
)
async def list_threads(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadResponse]:
    """List all threads for a workspace, newest first."""
    await _get_owned_workspace_by_id(workspace_id, current_user, db)
    result = await db.execute(
        select(Thread)
        .where(Thread.workspace_id == workspace_id)
        .order_by(Thread.updated_at.desc())
    )
    threads = result.scalars().all()
    return [ThreadResponse.model_validate(t) for t in threads]


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Fetch a thread. Returns 404 if not found or not owned by caller."""
    thread = await _get_thread_with_ownership(thread_id, current_user, db)
    return ThreadResponse.model_validate(thread)


# ── Message endpoints ──────────────────────────────────────────────────────────

@router.post(
    "/threads/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    thread_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Post a user message to the thread. Ownership verified via workspace."""
    thread = await _get_thread_with_ownership(thread_id, current_user, db)

    msg = Message(
        thread_id=thread.id,
        sender_type="user",
        sender_id=current_user.id,
        channel=body.channel,
        content=body.content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return _msg_to_response(msg)


@router.get("/threads/{thread_id}/messages", response_model=MessagePage)
async def list_messages(
    thread_id: uuid.UUID,
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor from previous response"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessagePage:
    """
    Return messages for a thread, oldest-first, cursor-paginated.

    Pass next_cursor from the previous response as ?cursor= to get the next page.
    next_cursor is None when there are no more messages.
    """
    thread = await _get_thread_with_ownership(thread_id, current_user, db)

    query = (
        select(Message)
        .where(Message.thread_id == thread.id)
        .order_by(Message.created_at, Message.id)
        .limit(limit)
    )

    if cursor:
        after_dt, after_id = _decode_cursor(cursor)
        query = query.where(
            (Message.created_at > after_dt)
            | ((Message.created_at == after_dt) & (Message.id > after_id))
        )

    result = await db.execute(query)
    msgs = result.scalars().all()

    next_cursor = _make_cursor(msgs[-1]) if len(msgs) == limit else None

    return MessagePage(
        items=[_msg_to_response(m) for m in msgs],
        next_cursor=next_cursor,
    )
