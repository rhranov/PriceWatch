"""
CRUD for data sources (websites).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ProductListing, Source
from backend.db.session import get_session_dependency

router = APIRouter()


class SourceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    base_url: str
    scraper_type: str
    is_active: bool
    rate_limit_seconds: float
    config: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceCreate(BaseModel):
    name: str
    slug: str
    base_url: str
    scraper_type: str = "playwright"
    is_active: bool = True
    rate_limit_seconds: float = 5.0
    config: dict[str, Any] = {}


@router.get("", response_model=list[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_session_dependency)):
    result = await db.execute(select(Source).order_by(Source.name))
    return [SourceOut.model_validate(s) for s in result.scalars().all()]


class SourceHealthOut(BaseModel):
    source_id: str
    source_name: str
    source_slug: str
    base_url: str
    is_active: bool
    total_listings: int
    scraped_24h: int
    scraped_7d: int
    never_scraped: int
    stale_listings: int
    success_rate_24h: int | None
    last_success: str | None
    status: Literal["healthy", "degraded", "failing", "no_listings"]


@router.get("/health", response_model=list[SourceHealthOut])
async def sources_health(db: AsyncSession = Depends(get_session_dependency)):
    """
    Per-source scraper reliability stats based on price_history records with a
    non-null price_eur. A scraper that returns None on every run shows 0% here.
    healthy  = ≥75% of active listings have a priced record in last 24h
    degraded = 25–74%
    failing  = <25% (or zero listings, or no priced records in 7d)
    """
    from sqlalchemy import func, case
    from backend.db.models import PriceHistory

    now = datetime.now(timezone.utc)
    cut_24h = now - timedelta(hours=24)
    cut_7d = now - timedelta(days=7)
    cut_stale = now - timedelta(hours=48)

    sources_res = await db.execute(select(Source).order_by(Source.name))
    sources = sources_res.scalars().all()

    result = []
    for src in sources:
        listings_res = await db.execute(
            select(ProductListing).where(
                ProductListing.source_id == src.id,
                ProductListing.is_active == True,
            )
        )
        listings = listings_res.scalars().all()

        total = len(listings)
        never_scraped = sum(1 for l in listings if l.last_scraped_at is None)
        stale = sum(1 for l in listings if not l.last_scraped_at or l.last_scraped_at < cut_stale)

        if total == 0:
            result.append(SourceHealthOut(
                source_id=str(src.id),
                source_name=src.name,
                source_slug=src.slug,
                base_url=src.base_url,
                is_active=src.is_active,
                total_listings=0,
                scraped_24h=0,
                scraped_7d=0,
                never_scraped=0,
                stale_listings=0,
                success_rate_24h=None,
                last_success=None,
                status="no_listings",
            ))
            continue

        listing_ids = [l.id for l in listings]

        # Count listings that produced a non-null price in each window.
        # This is the real success metric — last_scraped_at is set even when
        # the scraper returned None, making it useless for health assessment.
        ph_stats = (await db.execute(
            select(
                PriceHistory.listing_id,
                func.max(PriceHistory.scraped_at).filter(PriceHistory.price_eur.isnot(None)).label("last_priced_at"),
                func.count().filter(
                    PriceHistory.price_eur.isnot(None),
                    PriceHistory.scraped_at >= cut_24h,
                ).label("priced_24h"),
                func.count().filter(
                    PriceHistory.price_eur.isnot(None),
                    PriceHistory.scraped_at >= cut_7d,
                ).label("priced_7d"),
            )
            .where(PriceHistory.listing_id.in_(listing_ids))
            .group_by(PriceHistory.listing_id)
        )).all()

        stats_by_id = {str(row.listing_id): row for row in ph_stats}

        priced_24h = sum(1 for row in ph_stats if row.priced_24h > 0)
        priced_7d  = sum(1 for row in ph_stats if row.priced_7d > 0)

        last_ts_raw = max(
            (row.last_priced_at for row in ph_stats if row.last_priced_at),
            default=None,
        )

        rate = round(priced_24h / total * 100) if total > 0 else None

        if total == 0:
            status = "no_listings"
        elif priced_7d == 0:
            status = "failing"
        elif priced_24h == 0:
            status = "degraded"
        elif rate is not None and rate >= 75:
            status = "healthy"
        else:
            status = "degraded"

        result.append(SourceHealthOut(
            source_id=str(src.id),
            source_name=src.name,
            source_slug=src.slug,
            base_url=src.base_url,
            is_active=src.is_active,
            total_listings=total,
            scraped_24h=priced_24h,
            scraped_7d=priced_7d,
            never_scraped=never_scraped,
            stale_listings=stale,
            success_rate_24h=rate,
            last_success=last_ts_raw.isoformat() if last_ts_raw else None,
            status=status,
        ))

    return result


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(
    body: SourceCreate, db: AsyncSession = Depends(get_session_dependency)
):
    existing = await db.execute(select(Source).where(Source.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Source slug '{body.slug}' already exists")
    source = Source(**body.model_dump())
    db.add(source)
    await db.flush()
    return SourceOut.model_validate(source)


@router.patch("/{source_id}/toggle", response_model=SourceOut)
async def toggle_source(
    source_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source not found")
    source.is_active = not source.is_active
    return SourceOut.model_validate(source)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source not found")
    await db.delete(source)
