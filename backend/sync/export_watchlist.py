"""
Export the current watchlist to JSON so the scheduled Claude agent can read it
via the device bridge.

Writes data/sync/watchlist_export.json containing every active scope with its
linked sources, products, and listings (including each listing's last known
price and stock status, so the agent can detect changes).

Run manually:   python -m backend.sync.export_watchlist
Or on a timer:  scheduled hourly by backend/scheduler/jobs.py
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.db.models import (
    PriceHistory,
    Product,
    ProductListing,
    ProductScope,
    ScopeSource,
    Source,
)
from backend.db.session import get_session

# data/sync/ lives at the project root (two levels up from backend/sync/)
EXPORT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "sync" / "watchlist_export.json"
)


async def _last_price(session, listing_id) -> dict:
    """Most recent price record for a listing, for change detection by the agent."""
    res = await session.execute(
        select(PriceHistory)
        .where(PriceHistory.listing_id == listing_id)
        .order_by(PriceHistory.scraped_at.desc())
        .limit(1)
    )
    ph = res.scalar_one_or_none()
    if ph:
        return {
            "last_price_eur": ph.price_eur,
            "last_in_stock": ph.in_stock,
            "last_scraped_at": ph.scraped_at.isoformat() if ph.scraped_at else None,
        }
    return {"last_price_eur": None, "last_in_stock": None, "last_scraped_at": None}


async def build_export() -> dict:
    async with get_session() as session:
        res = await session.execute(
            select(ProductScope).where(ProductScope.is_active.is_(True))
        )
        scopes = res.scalars().all()

        scopes_out = []
        for scope in scopes:
            # Sources linked to this scope
            res_ss = await session.execute(
                select(ScopeSource, Source)
                .join(Source, ScopeSource.source_id == Source.id)
                .where(
                    ScopeSource.scope_id == scope.id,
                    ScopeSource.is_active.is_(True),
                    Source.is_active.is_(True),
                )
            )
            sources_out = [
                {
                    "slug": src.slug,
                    "name": src.name,
                    "base_url": src.base_url,
                    "scraper_type": src.scraper_type,
                    "search_url_template": ss.search_url_template,
                }
                for ss, src in res_ss.all()
            ]

            # Active products + their active listings
            res_p = await session.execute(
                select(Product).where(
                    Product.scope_id == scope.id, Product.status == "active"
                )
            )
            products_out = []
            for p in res_p.scalars().all():
                res_l = await session.execute(
                    select(ProductListing, Source)
                    .join(Source, ProductListing.source_id == Source.id)
                    .where(
                        ProductListing.product_id == p.id,
                        ProductListing.is_active.is_(True),
                    )
                )
                listings_out = []
                for listing, src in res_l.all():
                    last = await _last_price(session, listing.id)
                    listings_out.append(
                        {
                            "id": str(listing.id),
                            "source_slug": src.slug,
                            "source_name": src.name,
                            "listing_url": listing.listing_url,
                            "listing_title": listing.listing_title,
                            **last,
                        }
                    )
                products_out.append(
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "brand": p.brand,
                        "model": p.model,
                        "specs": p.specs,
                        "status": p.status,
                        "listings": listings_out,
                    }
                )

            scopes_out.append(
                {
                    "id": str(scope.id),
                    "name": scope.name,
                    "slug": scope.slug,
                    "description": scope.description,
                    "qualifier_rules": scope.qualifier_rules,
                    "search_terms": scope.search_terms,
                    "min_price_eur": scope.min_price_eur,
                    "max_price_eur": scope.max_price_eur,
                    "sources": sources_out,
                    "products": products_out,
                }
            )

        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "scope_count": len(scopes_out),
            "scopes": scopes_out,
        }


async def main():
    data = await build_export()
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    n_products = sum(len(s["products"]) for s in data["scopes"])
    n_listings = sum(
        len(p["listings"]) for s in data["scopes"] for p in s["products"]
    )
    print(
        f"Exported {data['scope_count']} scope(s), {n_products} product(s), "
        f"{n_listings} listing(s) -> {EXPORT_PATH}"
    )


if __name__ == "__main__":
    asyncio.run(main())
