"""
Research Intelligence API — market signals and future watch items.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ResearchSignal, ResearchWatch
from backend.db.session import get_session_dependency

router = APIRouter()


# ── Pydantic schemas ───────────────────────────────────────────────────────

class WatchOut(BaseModel):
    id: uuid.UUID
    signal_id: uuid.UUID
    watch_type: str
    title: str
    description: str | None
    target_url: str | None
    search_query: str | None
    check_by_date: str | None
    last_checked_at: datetime | None
    status: str
    result: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalOut(BaseModel):
    id: uuid.UUID
    discovered_at: datetime
    run_id: uuid.UUID | None
    signal_type: str
    significance: str
    title: str
    summary: str | None
    source_platform: str | None
    source_url: str | None
    source_author: str | None
    product_id: uuid.UUID | None
    scope_slug: str | None
    action_required: bool
    action_description: str | None
    follow_up_date: str | None
    status: str
    notes: str | None
    watches: list[WatchOut] = []

    model_config = {"from_attributes": True}


class WatchCreate(BaseModel):
    watch_type: str
    title: str
    description: str | None = None
    target_url: str | None = None
    search_query: str | None = None
    check_by_date: str | None = None


class SignalCreate(BaseModel):
    signal_type: str
    significance: str = "medium"
    title: str
    summary: str | None = None
    source_platform: str | None = None
    source_url: str | None = None
    source_author: str | None = None
    product_id: uuid.UUID | None = None
    scope_slug: str | None = None
    action_required: bool = False
    action_description: str | None = None
    follow_up_date: str | None = None
    status: str = "new"
    notes: str | None = None
    raw_data: dict[str, Any] = {}
    discovered_at: datetime | None = None
    watches: list[WatchCreate] = []


class SignalPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    action_required: bool | None = None
    action_description: str | None = None
    follow_up_date: str | None = None
    significance: str | None = None
    summary: str | None = None


class WatchPatch(BaseModel):
    status: str | None = None
    result: str | None = None
    last_checked_at: datetime | None = None


# ── Signal endpoints ───────────────────────────────────────────────────────

@router.get("/signals", response_model=list[SignalOut])
async def list_signals(
    signal_type: str | None = Query(None),
    significance: str | None = Query(None),
    status: str | None = Query(None),
    product_id: uuid.UUID | None = Query(None),
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_session_dependency),
):
    q = (
        select(ResearchSignal)
        .options(selectinload(ResearchSignal.watches))
        .order_by(desc(ResearchSignal.discovered_at))
        .limit(limit)
    )
    if signal_type:
        q = q.where(ResearchSignal.signal_type == signal_type)
    if significance:
        q = q.where(ResearchSignal.significance == significance)
    if status:
        q = q.where(ResearchSignal.status == status)
    if product_id:
        q = q.where(ResearchSignal.product_id == product_id)
    result = await db.execute(q)
    return [SignalOut.model_validate(s) for s in result.scalars().all()]


@router.post("/signals", response_model=SignalOut, status_code=201)
async def create_signal(
    body: SignalCreate,
    db: AsyncSession = Depends(get_session_dependency),
):
    sig = ResearchSignal(
        signal_type=body.signal_type,
        significance=body.significance,
        title=body.title,
        summary=body.summary,
        source_platform=body.source_platform,
        source_url=body.source_url,
        source_author=body.source_author,
        product_id=body.product_id,
        scope_slug=body.scope_slug,
        action_required=body.action_required,
        action_description=body.action_description,
        follow_up_date=body.follow_up_date,
        status=body.status,
        notes=body.notes,
        raw_data=body.raw_data,
    )
    if body.discovered_at:
        sig.discovered_at = body.discovered_at
    db.add(sig)
    await db.flush()

    for w in body.watches:
        db.add(ResearchWatch(
            signal_id=sig.id,
            watch_type=w.watch_type,
            title=w.title,
            description=w.description,
            target_url=w.target_url,
            search_query=w.search_query,
            check_by_date=w.check_by_date,
        ))

    await db.flush()

    result = await db.execute(
        select(ResearchSignal)
        .options(selectinload(ResearchSignal.watches))
        .where(ResearchSignal.id == sig.id)
    )
    return SignalOut.model_validate(result.scalar_one())


@router.get("/signals/{signal_id}", response_model=SignalOut)
async def get_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(ResearchSignal)
        .options(selectinload(ResearchSignal.watches))
        .where(ResearchSignal.id == signal_id)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(404, "Signal not found")
    return SignalOut.model_validate(sig)


@router.patch("/signals/{signal_id}", response_model=SignalOut)
async def update_signal(
    signal_id: uuid.UUID,
    body: SignalPatch,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(ResearchSignal)
        .options(selectinload(ResearchSignal.watches))
        .where(ResearchSignal.id == signal_id)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(404, "Signal not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sig, field, value)
    return SignalOut.model_validate(sig)


# ── Watch endpoints ────────────────────────────────────────────────────────

@router.get("/watches", response_model=list[WatchOut])
async def list_watches(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_session_dependency),
):
    q = select(ResearchWatch)
    if status:
        q = q.where(ResearchWatch.status == status)
    q = (
        q.order_by(asc(ResearchWatch.check_by_date).nulls_last(), asc(ResearchWatch.created_at))
        .limit(limit)
    )
    result = await db.execute(q)
    return [WatchOut.model_validate(w) for w in result.scalars().all()]


@router.patch("/watches/{watch_id}", response_model=WatchOut)
async def update_watch(
    watch_id: uuid.UUID,
    body: WatchPatch,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(select(ResearchWatch).where(ResearchWatch.id == watch_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Watch not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(w, field, value)
    return WatchOut.model_validate(w)
