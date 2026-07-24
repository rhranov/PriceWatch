"""
Endpoints for pending discoveries — new products found by the research agent.
User approves or rejects them here.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import PendingDiscovery, Product, ProductListing, ProductScope, Source
from backend.db.session import get_session_dependency

router = APIRouter()


class DiscoveryOut(BaseModel):
    id: uuid.UUID
    scope_id: uuid.UUID
    name: str
    brand: str | None
    model: str | None
    specs: dict[str, Any]
    source_name: str | None
    source_url: str | None
    price_eur: float | None
    in_stock: bool | None
    ships_to_germany: bool | None
    screenshot_path: str | None
    ai_reasoning: str | None
    status: str
    found_at: datetime

    model_config = {"from_attributes": True}


class ReviewBody(BaseModel):
    action: str  # "approve" | "reject"
    notes: str | None = None
    # If approving, optionally provide listing URLs to add immediately
    listing_urls: list[dict[str, str]] = []  # [{source_slug, url}]


class CreateDiscoveryBody(BaseModel):
    product_name: str
    brand: str | None = None
    model: str | None = None
    scope_slug: str
    source_slug: str
    listing_url: str
    price_eur: float
    in_stock: bool
    notes: str | None = None
    confidence: str = "medium"  # high | medium | low


@router.post("/create", response_model=DiscoveryOut, status_code=201)
async def create_discovery(
    body: CreateDiscoveryBody,
    db: AsyncSession = Depends(get_session_dependency),
):
    """
    Submit a verified product discovery from the an external agent research session.
    Used when the direct integration is unavailable (e.g. unavailable integration).
    """
    scope = (await db.execute(
        select(ProductScope).where(ProductScope.slug == body.scope_slug)
    )).scalar_one_or_none()
    if not scope:
        raise HTTPException(400, f"Unknown scope slug: {body.scope_slug}")

    source = (await db.execute(
        select(Source).where(Source.slug == body.source_slug)
    )).scalar_one_or_none()
    source_name = source.name if source else body.source_slug

    # Live verification — fetch the URL to get real price and in_stock, reject if unavailable.
    from backend.scrapers.verify import verify_listing_url
    v_ok, v_price, v_title, v_in_stock, v_error = await verify_listing_url(
        body.source_slug, body.listing_url, expected_product_name=body.product_name
    )
    if not v_ok:
        raise HTTPException(422, f"URL verification failed: {v_error}")
    if v_price is None:
        raise HTTPException(422, f"No price found on listing page (title: '{v_title}'). Product may be unavailable.")

    status = "pending"

    disc = PendingDiscovery(
        scope_id=scope.id,
        name=body.product_name,
        brand=body.brand,
        model=body.model,
        source_name=source_name,
        source_url=body.listing_url,
        price_eur=v_price,
        in_stock=v_in_stock,
        ai_reasoning=body.notes,
        status=status,
    )
    db.add(disc)
    await db.commit()
    await db.refresh(disc)
    return DiscoveryOut.model_validate(disc)


@router.get("/count/pending")
async def count_pending(db: AsyncSession = Depends(get_session_dependency)):
    result = await db.execute(
        select(PendingDiscovery).where(PendingDiscovery.status == "pending")
    )
    return {"count": len(result.scalars().all())}


@router.get("", response_model=list[DiscoveryOut])
async def list_discoveries(
    status: str = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=200),
    scope_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_session_dependency),
):
    q = select(PendingDiscovery).where(PendingDiscovery.status == status)
    if scope_id:
        q = q.where(PendingDiscovery.scope_id == scope_id)
    q = q.order_by(desc(PendingDiscovery.found_at)).limit(limit)
    result = await db.execute(q)
    return [DiscoveryOut.model_validate(d) for d in result.scalars().all()]


@router.get("/{discovery_id}", response_model=DiscoveryOut)
async def get_discovery(
    discovery_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(
        select(PendingDiscovery).where(PendingDiscovery.id == discovery_id)
    )
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Discovery not found")
    return DiscoveryOut.model_validate(d)



@router.post("/{discovery_id}/review", response_model=DiscoveryOut)
async def review_discovery(
    discovery_id: uuid.UUID,
    body: ReviewBody,
    db: AsyncSession = Depends(get_session_dependency),
):
    """
    Approve → creates a Product from the discovery and adds any provided listings.
    Reject → marks as rejected.
    """
    result = await db.execute(
        select(PendingDiscovery).where(PendingDiscovery.id == discovery_id)
    )
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Discovery not found")
    if d.status != "pending":
        raise HTTPException(400, f"Discovery already {d.status}")

    if body.action == "approve":
        # Create product from discovery
        product = Product(
            scope_id=d.scope_id,
            name=d.name,
            brand=d.brand,
            model=d.model,
            specs=d.specs,
            notes=f"Auto-added from discovery on {d.found_at.date()}. {body.notes or ''}".strip(),
            status="active",
        )
        db.add(product)
        await db.flush()

        # Add the discovery source URL as a listing
        if d.source_url and d.source_name:
            source_result = await db.execute(
                select(Source).where(Source.name == d.source_name)
            )
            source = source_result.scalar_one_or_none()
            if source:
                listing = ProductListing(
                    product_id=product.id,
                    source_id=source.id,
                    listing_url=d.source_url,
                    listing_title=d.name,
                    is_primary=True,
                )
                db.add(listing)

        d.status = "approved"
        d.reviewed_at = datetime.now(timezone.utc)
        d.review_notes = body.notes

    elif body.action == "reject":
        d.status = "rejected"
        d.reviewed_at = datetime.now(timezone.utc)
        d.review_notes = body.notes
    else:
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    return DiscoveryOut.model_validate(d)
