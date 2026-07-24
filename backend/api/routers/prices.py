"""
Price history queries — time-series data for dashboard charts.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import PriceHistory, ProductListing
from backend.db.session import get_session_dependency

router = APIRouter()


class PricePoint(BaseModel):
    scraped_at: datetime
    price_eur: float | None
    in_stock: bool | None
    ships_to_germany: bool | None
    source_id: uuid.UUID
    source_name: str
    listing_id: uuid.UUID

    model_config = {"from_attributes": True}


class PriceSummary(BaseModel):
    listing_id: uuid.UUID
    product_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    current_price_eur: float | None
    min_price_eur: float | None
    max_price_eur: float | None
    price_7d_ago: float | None
    change_pct: float | None
    is_available: bool | None
    last_checked: datetime | None
    is_all_time_low: bool


@router.delete("/history/listing/{listing_id}", status_code=204)
async def delete_listing_price_history(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_dependency),
):
    """Delete ALL price history for a listing — use when recorded data is known bad."""
    await db.execute(delete(PriceHistory).where(PriceHistory.listing_id == listing_id))


@router.delete("/history/{record_id}", status_code=204)
async def delete_price_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_dependency),
):
    """Delete a single price_history record by ID."""
    result = await db.execute(select(PriceHistory).where(PriceHistory.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Price record not found")
    await db.delete(record)


@router.get("/history/{listing_id}", response_model=list[PricePoint])
async def get_price_history(
    listing_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_session_dependency),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PriceHistory)
        .options(selectinload(PriceHistory.listing).selectinload(ProductListing.source))
        .where(PriceHistory.listing_id == listing_id, PriceHistory.scraped_at >= since)
        .order_by(PriceHistory.scraped_at)
    )
    rows = result.scalars().all()
    return [
        PricePoint(
            scraped_at=r.scraped_at,
            price_eur=r.price_eur,
            in_stock=r.in_stock,
            ships_to_germany=r.ships_to_germany,
            source_id=r.listing.source_id,
            source_name=r.listing.source.name if r.listing.source else "Unknown",
            listing_id=r.listing_id,
        )
        for r in rows
        if r.listing is not None
    ]


@router.get("/product/{product_id}/summary", response_model=list[PriceSummary])
async def get_product_price_summary(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_dependency),
):
    """Per-source price stats: current price, 7-day change, all-time low/high."""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    listings_result = await db.execute(
        select(ProductListing)
        .options(selectinload(ProductListing.source))
        .where(ProductListing.product_id == product_id, ProductListing.is_active == True)
    )
    listings = listings_result.scalars().all()

    summaries = []
    for listing in listings:
        latest = (await db.execute(
            select(PriceHistory)
            .where(PriceHistory.listing_id == listing.id)
            .order_by(desc(PriceHistory.scraped_at))
            .limit(1)
        )).scalar_one_or_none()

        stats = (await db.execute(
            select(func.min(PriceHistory.price_eur), func.max(PriceHistory.price_eur))
            .where(PriceHistory.listing_id == listing.id, PriceHistory.price_eur.isnot(None))
        )).one_or_none()

        price_7d = (await db.execute(
            select(PriceHistory.price_eur)
            .where(
                PriceHistory.listing_id == listing.id,
                PriceHistory.scraped_at <= seven_days_ago,
                PriceHistory.price_eur.isnot(None),
            )
            .order_by(desc(PriceHistory.scraped_at))
            .limit(1)
        )).scalar_one_or_none()

        current = latest.price_eur if latest else None
        min_p = stats[0] if stats else None
        max_p = stats[1] if stats else None
        change_pct = None
        if current and price_7d and price_7d > 0:
            change_pct = round((current - price_7d) / price_7d * 100, 1)

        summaries.append(PriceSummary(
            listing_id=listing.id,
            product_id=product_id,
            source_id=listing.source_id,
            source_name=listing.source.name if listing.source else "Unknown",
            current_price_eur=current,
            min_price_eur=min_p,
            max_price_eur=max_p,
            price_7d_ago=price_7d,
            change_pct=change_pct,
            is_available=listing.is_available,
            last_checked=listing.last_scraped_at,
            is_all_time_low=bool(current is not None and min_p is not None and abs(current - min_p) < 0.01),
        ))

    return summaries


@router.get("/product/{product_id}", response_model=list[PricePoint])
async def get_product_prices(
    product_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_session_dependency),
):
    """All price history across all listings for a product, with correct source info."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    listings_result = await db.execute(
        select(ProductListing)
        .options(selectinload(ProductListing.source))
        .where(ProductListing.product_id == product_id, ProductListing.is_active == True)
    )
    listings = listings_result.scalars().all()
    listing_map = {l.id: l for l in listings}

    if not listing_map:
        return []

    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.listing_id.in_(list(listing_map)), PriceHistory.scraped_at >= since)
        .order_by(PriceHistory.scraped_at)
    )
    rows = result.scalars().all()
    return [
        PricePoint(
            scraped_at=r.scraped_at,
            price_eur=r.price_eur,
            in_stock=r.in_stock,
            ships_to_germany=r.ships_to_germany,
            source_id=listing_map[r.listing_id].source_id if r.listing_id in listing_map else uuid.uuid4(),
            source_name=(listing_map[r.listing_id].source.name if r.listing_id in listing_map and listing_map[r.listing_id].source else "Unknown"),
            listing_id=r.listing_id,
        )
        for r in rows
    ]
