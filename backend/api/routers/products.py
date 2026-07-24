"""
CRUD endpoints for products and their listings.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import Product, ProductListing, Source
from backend.db.session import get_session_dependency

router = APIRouter()


# --- Schemas ---

class ListingOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str = ""
    listing_url: str
    listing_title: str | None
    is_primary: bool
    is_active: bool
    last_scraped_at: datetime | None
    last_verified_at: datetime | None
    is_available: bool | None
    latest_price_eur: float | None = None

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: uuid.UUID
    scope_id: uuid.UUID
    name: str
    brand: str | None
    model: str | None
    specs: dict[str, Any]
    status: str
    notes: str | None
    image_url: str | None
    added_at: datetime
    listings: list[ListingOut] = []
    lowest_price_eur: float | None = None

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    scope_id: uuid.UUID
    name: str
    brand: str | None = None
    model: str | None = None
    specs: dict[str, Any] = {}
    status: str = "active"
    notes: str | None = None
    image_url: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    specs: dict[str, Any] | None = None
    status: str | None = None
    notes: str | None = None
    image_url: str | None = None


class ListingCreate(BaseModel):
    source_id: uuid.UUID
    listing_url: str
    listing_title: str | None = None
    is_primary: bool = False


# --- Endpoints ---

@router.get("", response_model=list[ProductOut])
async def list_products(
    scope_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_session_dependency),
):
    q = select(Product).options(
        selectinload(Product.listings).selectinload(ProductListing.source)
    )
    if scope_id:
        q = q.where(Product.scope_id == scope_id)
    if status:
        q = q.where(Product.status == status)
    result = await db.execute(q)
    products = result.scalars().all()

    from sqlalchemy import desc, func
    from backend.db.models import PriceHistory

    # Collect all listing IDs across all products in one pass, then fetch
    # the latest price for each listing in a single query instead of N queries.
    all_listing_ids = [l.id for p in products for l in p.listings]
    latest_prices: dict[str, float | None] = {}
    if all_listing_ids:
        # DISTINCT ON gives the most-recent row per listing_id in one round-trip.
        ph_rows = (await db.execute(
            select(PriceHistory.listing_id, PriceHistory.price_eur)
            .distinct(PriceHistory.listing_id)
            .where(PriceHistory.listing_id.in_(all_listing_ids))
            .order_by(PriceHistory.listing_id, desc(PriceHistory.scraped_at))
        )).all()
        latest_prices = {str(row.listing_id): row.price_eur for row in ph_rows}

    out = []
    for p in products:
        listings_out = []
        lowest = None
        for listing in p.listings:
            price = latest_prices.get(str(listing.id))
            if price and (lowest is None or price < lowest):
                lowest = price
            listings_out.append(
                ListingOut(
                    id=listing.id,
                    source_id=listing.source_id,
                    source_name=listing.source.name if listing.source else "",
                    listing_url=listing.listing_url,
                    listing_title=listing.listing_title,
                    is_primary=listing.is_primary,
                    is_active=listing.is_active,
                    last_scraped_at=listing.last_scraped_at,
                    last_verified_at=listing.last_verified_at,
                    is_available=listing.is_available,
                    latest_price_eur=price,
                )
            )
        out.append(
            ProductOut(
                id=p.id,
                scope_id=p.scope_id,
                name=p.name,
                brand=p.brand,
                model=p.model,
                specs=p.specs,
                status=p.status,
                notes=p.notes,
                image_url=p.image_url,
                added_at=p.added_at,
                listings=listings_out,
                lowest_price_eur=lowest,
            )
        )
    return out


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate, db: AsyncSession = Depends(get_session_dependency)
):
    product = Product(**body.model_dump())
    db.add(product)
    await db.flush()
    return ProductOut(
        id=product.id,
        scope_id=product.scope_id,
        name=product.name,
        brand=product.brand,
        model=product.model,
        specs=product.specs,
        status=product.status,
        notes=product.notes,
        image_url=product.image_url,
        added_at=product.added_at,
    )


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.listings).selectinload(ProductListing.source))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    return ProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.listings).selectinload(ProductListing.source))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(product, field, value)
    from sqlalchemy import desc
    from backend.db.models import PriceHistory
    listing_ids = [l.id for l in product.listings]
    latest_prices: dict[str, float | None] = {}
    if listing_ids:
        ph_rows = (await db.execute(
            select(PriceHistory.listing_id, PriceHistory.price_eur)
            .distinct(PriceHistory.listing_id)
            .where(PriceHistory.listing_id.in_(listing_ids))
            .order_by(PriceHistory.listing_id, desc(PriceHistory.scraped_at))
        )).all()
        latest_prices = {str(row.listing_id): row.price_eur for row in ph_rows}
    listings_out = []
    lowest = None
    for listing in product.listings:
        price = latest_prices.get(str(listing.id))
        if price and (lowest is None or price < lowest):
            lowest = price
        listings_out.append(ListingOut(
            id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source.name if listing.source else "",
            listing_url=listing.listing_url,
            listing_title=listing.listing_title,
            is_primary=listing.is_primary,
            is_active=listing.is_active,
            last_scraped_at=listing.last_scraped_at,
            last_verified_at=listing.last_verified_at,
            is_available=listing.is_available,
            latest_price_eur=price,
        ))
    return ProductOut(
        id=product.id,
        scope_id=product.scope_id,
        name=product.name,
        brand=product.brand,
        model=product.model,
        specs=product.specs,
        status=product.status,
        notes=product.notes,
        image_url=product.image_url,
        added_at=product.added_at,
        listings=listings_out,
        lowest_price_eur=lowest,
    )


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_session_dependency)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    await db.delete(product)


@router.delete("/{product_id}/listings/{listing_id}", status_code=204)
async def delete_listing(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(ProductListing).where(
            ProductListing.id == listing_id,
            ProductListing.product_id == product_id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    await db.delete(listing)


class ListingPatch(BaseModel):
    listing_url: str | None = None
    listing_title: str | None = None
    is_primary: bool | None = None
    is_active: bool | None = None


@router.patch("/{product_id}/listings/{listing_id}", response_model=ListingOut)
async def update_listing(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    body: ListingPatch,
    db: AsyncSession = Depends(get_session_dependency),
):
    result = await db.execute(
        select(ProductListing)
        .where(ProductListing.id == listing_id, ProductListing.product_id == product_id)
        .options(selectinload(ProductListing.source))
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(listing, field, value)
    from backend.db.models import PriceHistory
    from sqlalchemy import desc
    ph = (await db.execute(
        select(PriceHistory).where(PriceHistory.listing_id == listing.id).order_by(desc(PriceHistory.scraped_at)).limit(1)
    )).scalar_one_or_none()
    return ListingOut(
        id=listing.id,
        source_id=listing.source_id,
        source_name=listing.source.name if listing.source else "",
        listing_url=listing.listing_url,
        listing_title=listing.listing_title,
        is_primary=listing.is_primary,
        is_active=listing.is_active,
        last_scraped_at=listing.last_scraped_at,
        last_verified_at=listing.last_verified_at,
        is_available=listing.is_available,
        latest_price_eur=ph.price_eur if ph else None,
    )


@router.post("/{product_id}/listings", response_model=ListingOut, status_code=201)
async def add_listing(
    product_id: uuid.UUID,
    body: ListingCreate,
    db: AsyncSession = Depends(get_session_dependency),
):
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    source = (await db.execute(select(Source).where(Source.id == body.source_id))).scalar_one_or_none()
    if not source:
        raise HTTPException(400, "Unknown source_id")

    # Live verification — confirm the URL resolves to a real product page before adding.
    # Price may be None (product temporarily unavailable) but title must be non-empty.
    from backend.scrapers.verify import verify_listing_url
    v_ok, v_price, v_title, v_in_stock, v_error = await verify_listing_url(
        source.slug, body.listing_url, expected_product_name=product.name
    )
    if not v_ok:
        raise HTTPException(422, f"URL verification failed: {v_error}")
    if not v_title:
        raise HTTPException(422, "URL returned no product title — may point to the wrong page or require authentication")

    listing = ProductListing(product_id=product_id, **body.model_dump())
    db.add(listing)
    await db.flush()

    return ListingOut(
        id=listing.id,
        source_id=listing.source_id,
        source_name=source.name,
        listing_url=listing.listing_url,
        listing_title=listing.listing_title,
        is_primary=listing.is_primary,
        is_active=listing.is_active,
        last_scraped_at=None,
        last_verified_at=None,
        is_available=None,
    )
