"""
Agent run history endpoints.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AgentRun
from backend.db.session import get_session_dependency

log = structlog.get_logger(__name__)
router = APIRouter()


class RunOut(BaseModel):
    id: uuid.UUID
    run_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    scopes_checked: list[str]
    products_checked: int
    prices_updated: int
    price_changes: list[dict]
    discoveries_found: int
    errors: list[dict]
    data_checks: list[dict]
    tokens_used: dict[str, Any]

    model_config = {"from_attributes": True}


@router.get("", response_model=list[RunOut])
async def list_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(AgentRun).order_by(desc(AgentRun.started_at)).limit(limit)
    )
    return [RunOut.model_validate(r) for r in result.scalars().all()]


@router.get("/latest", response_model=RunOut | None)
async def latest_run(db: AsyncSession = Depends(get_session_dependency)):
    result = await db.execute(
        select(AgentRun).order_by(desc(AgentRun.started_at)).limit(1)
    )
    run = result.scalar_one_or_none()
    return RunOut.model_validate(run) if run else None


@router.post("/trigger")
async def trigger_price_check():
    """Trigger an immediate price check run (runs in background)."""
    from backend.scheduler.jobs import start_price_check_background
    if not await start_price_check_background():
        raise HTTPException(409, "A price check is already running")
    return {"status": "triggered"}


@router.post("/research")
async def trigger_deep_research():
    """
    Deep research is performed by an external agent directly in the external workflow.
    This endpoint no longer triggers a backend job — use /runs/start + /runs/{id}/finish
    to register an in-session research run in the Activity tab.
    """
    from fastapi import HTTPException
    raise HTTPException(
        410,
        "Deep research runs in an external agent, not the backend. "
        "Start one in the external workflow and register it via POST /api/runs/start.",
    )


@router.post("/start")
async def start_agent_run(
    run_type: str = "deep_research",
    db: AsyncSession = Depends(get_session_dependency),
):
    """
    Create an AgentRun record in 'running' state.
    Called by an external agent at the start of an in-session research or price check
    so the Activity tab reflects what is happening in real time.
    Returns the run_id to pass back to /runs/{id}/finish.
    """
    run = AgentRun(run_type=run_type, status="running")
    db.add(run)
    await db.flush()
    run_id = str(run.id)
    await db.commit()
    return {"run_id": run_id, "status": "running", "run_type": run_type}


class RunFinishIn(BaseModel):
    status: str = "completed"           # completed | completed_with_errors | failed
    discoveries_found: int = 0
    products_checked: int = 0
    prices_updated: int = 0
    price_changes: list[dict] = []
    errors: list[dict] = []
    summary: str = ""


@router.post("/{run_id}/finish")
async def finish_agent_run(
    run_id: uuid.UUID,
    body: RunFinishIn,
    db: AsyncSession = Depends(get_session_dependency),
):
    """
    Mark an AgentRun as finished. Called by an external agent at the end of an
    in-session run so the Activity tab shows the final status and counts.
    """
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    run.status           = body.status
    run.finished_at      = datetime.now(timezone.utc)
    run.discoveries_found = body.discoveries_found
    run.products_checked = body.products_checked
    run.prices_updated   = body.prices_updated
    run.price_changes    = body.price_changes
    run.errors           = body.errors
    run.log_text         = body.summary or None
    await db.commit()
    return {"run_id": str(run_id), "status": run.status}


@router.get("/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")
    return RunOut.model_validate(run)
