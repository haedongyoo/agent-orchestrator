from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.db.session import get_db

router = APIRouter()


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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/approvals", response_model=List[ApprovalResponse])
async def list_approvals(
    workspace_id: uuid.UUID,
    status: Optional[str] = Query(None, description="Filter by status: pending | approved | rejected"),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(approval_id: uuid.UUID, body: ApprovalDecision, db: AsyncSession = Depends(get_db)):
    # Approve and unblock the waiting orchestrator step
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def reject(approval_id: uuid.UUID, body: ApprovalDecision, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Not implemented")
