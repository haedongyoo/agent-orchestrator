from __future__ import annotations
"""
Approvals router — list, approve, reject.

Endpoints (all require Bearer JWT):
  GET   /api/workspaces/{id}/approvals?status=pending  → 200 [ApprovalResponse]
  POST  /api/approvals/{id}/approve                    → 200 ApprovalResponse
  POST  /api/approvals/{id}/reject                     → 200 ApprovalResponse
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.db.session import get_db
from app.models.approval import Approval, APPROVAL_STATUSES
from app.models.workspace import Workspace, User
from app.services.auth import get_current_user

router = APIRouter()

_VALID_STATUSES = frozenset(APPROVAL_STATUSES)


# ── Schemas ────────────────────────────────────────────────────────────────────

class ApprovalResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    approval_type: str
    requested_by: uuid.UUID
    scope: dict
    status: str
    reason: Optional[str]

    class Config:
        from_attributes = True


class ApprovalDecision(BaseModel):
    note: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_owned_workspace(
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


async def _get_approval(
    approval_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Approval:
    """Load approval and verify workspace ownership."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    # Verify workspace ownership
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == approval.workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    if ws_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    return approval


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/approvals", response_model=List[ApprovalResponse])
async def list_approvals(
    workspace_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending | approved | rejected"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List approvals for a workspace, optionally filtered by status."""
    await _get_owned_workspace(workspace_id, current_user, db)

    query = select(Approval).where(Approval.workspace_id == workspace_id)

    if status_filter:
        if status_filter not in _VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status '{status_filter}'. Must be one of: {sorted(_VALID_STATUSES)}",
            )
        query = query.where(Approval.status == status_filter)

    query = query.order_by(Approval.created_at.desc())
    result = await db.execute(query)
    approvals = result.scalars().all()
    return [ApprovalResponse.model_validate(a) for a in approvals]


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending approval request."""
    approval = await _get_approval(approval_id, current_user, db)

    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval is already {approval.status}",
        )

    approval.status = "approved"
    approval.approved_by = current_user.id
    approval.decided_at = datetime.now(timezone.utc)
    if body.note:
        approval.reason = body.note

    await db.commit()
    await db.refresh(approval)
    return ApprovalResponse.model_validate(approval)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending approval request."""
    approval = await _get_approval(approval_id, current_user, db)

    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval is already {approval.status}",
        )

    approval.status = "rejected"
    approval.approved_by = current_user.id
    approval.decided_at = datetime.now(timezone.utc)
    if body.note:
        approval.reason = body.note

    await db.commit()
    await db.refresh(approval)
    return ApprovalResponse.model_validate(approval)
