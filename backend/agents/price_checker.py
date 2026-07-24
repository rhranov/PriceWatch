"""
Price Checker — monitors known product listings for price changes.
Uses scrapers directly; no LLM calls.

On each run:
1. Auto-discovers missing listings (any source linked to a product's scope that
   has no listing for that product is searched automatically).
2. Checks all active listings for current prices.
3. Writes all events to data/agent_log.jsonl for the next session's briefing.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agent_log import log_event
from backend.db.models import (
    PriceHistory,
    Product,
    ProductListing,
    ProductScope,
    ScopeSource,
    Source,
)
from backend.scrapers.registry import get_scraper

log = structlog.get_logger(__name__)

PRICE_CHANGE_THRESHOLD  = 0.02   # 2%  — flag as significant change
LISTING_MATCH_THRESHOLD = 0.55


def _score_match(result_title: str, product: Product) -> float:
    title = result_title.lower()
    tokens: set[str] = set()

    if product.brand:
        for w in product.brand.lower().split():
            tokens.add(w)
    if product.model:
        for w in product.model.lower().split():
            if len(w) > 1:
                tokens.add(w)

    specs = product.specs or {}
    mem = specs.get("unified_memory_gb")
    if mem:
        tokens.add(f"{mem}gb")

    stopwords = {"the", "a", "an", "and", "or", "for", "of", "in", "with", "mini", "pc", "desktop"}
    tokens -= stopwords

    if not tokens:
        return 0.0

    brand_tokens = {w.lower() for w in (product.brand or "").split() if w}
    if brand_tokens and not any(bt in title for bt in brand_tokens):
        return 0.0

    matched = sum(1 for t in tokens if t in title)
    return matched / len(tokens)


class PriceCheckerAgent:

    async def discover_missing_listings(self, session: AsyncSession) -> dict[str, Any]:
        """
        For every (product, source) pair linked via scope_sources that has no
        product_listing, search the source and auto-create a listing if a
        confident title match is found.
        """
        products_res = await session.execute(
            select(Product)
            .options(selectinload(Product.listings))
            .where(Product.status == "active")
        )
        products = products_res.scalars().all()

        ss_res = await session.execute(
            select(ScopeSource, Source)
            .join(Source, Source.id == ScopeSource.source_id)
            .where(ScopeSource.is_active == True, Source.is_active == True)
        )
        scope_sources = ss_res.all()

        existing_res = await session.execute(
            select(ProductListing.product_id, ProductListing.source_id)
            .where(ProductListing.is_active == True)
        )
        existing_pairs = {(str(r.product_id), str(r.source_id)) for r in existing_res}

        missing: list[tuple[Product, Source]] = []
        for product in products:
            for ss, source in scope_sources:
                if ss.scope_id != product.scope_id:
                    continue
                if (source.config or {}).get("skip_auto_discovery"):
                    continue
                pair_key = (str(product.id), str(source.id))
                if pair_key not in existing_pairs:
                    missing.append((product, source))

        if not missing:
            log.info("Listing discovery: no missing listings")
            return {"discovered": 0, "errors": []}

        log.info("Listing discovery: searching for missing listings", count=len(missing))
        discovered = 0
        errors = []

        for product, source in missing:
            scraper = get_scraper(source.slug)
            if not scraper or not hasattr(scraper, "search"):
                continue

            query = f"{product.brand or ''} {product.model or product.name}".strip()
            try:
                results = await scraper.search(query, max_results=8)
            except Exception as e:
                log.warning("Listing discovery: search failed", source=source.slug, error=str(e))
                errors.append({"source": source.slug, "product": product.name, "error": str(e)})
                await log_event(
                    "SCRAPER FAIL",
                    f"{source.slug} | {product.name}: search() raised exception: {str(e)[:120]}",
                )
                continue

            best = None
            best_score = 0.0
            for r in results:
                score = _score_match(r.title, product)
                if score > best_score:
                    best_score = score
                    best = r

            if best and best_score >= LISTING_MATCH_THRESHOLD:
                dupe_res = await session.execute(
                    select(ProductListing.id).where(
                        ProductListing.product_id == product.id,
                        ProductListing.source_id == source.id,
                        ProductListing.listing_url == best.url,
                    )
                )
                if dupe_res.scalar_one_or_none() is not None:
                    continue

                # Verify the URL returns a real product page before accepting it.
                # Title match on search results is necessary but not sufficient —
                # the actual product page may differ or return no data.
                from backend.scrapers.verify import verify_listing_url
                v_ok, v_price, v_title, v_in_stock, v_error = await verify_listing_url(
                    source.slug, best.url, expected_product_name=product.name
                )
                if not v_ok:
                    log.warning(
                        "Listing discovery: URL verification failed — skipping",
                        source=source.slug, product=product.name,
                        url=best.url, error=v_error,
                    )
                    errors.append({
                        "source": source.slug,
                        "product": product.name,
                        "url": best.url,
                        "error": f"URL verification failed: {v_error}",
                    })
                    await log_event(
                        "SCRAPER FAIL",
                        f"{source.slug} | {product.name}: auto-discovery URL verification failed: {v_error}",
                    )
                    continue

                listing = ProductListing(
                    product_id=product.id,
                    source_id=source.id,
                    listing_url=best.url,
                    listing_title=(v_title[:490] if v_title else product.name),
                    is_primary=False,
                )
                session.add(listing)
                await session.flush()
                discovered += 1
                log.info("Listing discovery: created", source=source.name,
                         product=product.name, url=best.url, score=round(best_score, 2),
                         verified_price=v_price)

            await asyncio.sleep(1)

        return {"discovered": discovered, "errors": errors}

    async def check_all_listings(
        self,
        session: AsyncSession,
        run_id: str,
        progress_callback=None,
    ) -> dict[str, Any]:

        discovery = await self.discover_missing_listings(session)

        result = await session.execute(
            select(ProductListing)
            .options(
                selectinload(ProductListing.source),
                selectinload(ProductListing.product),
            )
            .where(ProductListing.is_active == True)
        )
        listings = result.scalars().all()

        await log_event("PRICE CHECK START", f"{len(listings)} listings to check", run_id=run_id)
        log.info("Price checker: checking listings", count=len(listings))

        updated = 0
        changes = []
        errors  = list(discovery.get("errors", []))

        for listing in listings:
            prod_name = listing.product.name if listing.product else listing.listing_title or "?"
            try:
                result_row = await self._check_listing(listing, session)
                if result_row:
                    if result_row.get("price_changed"):
                        updated += 1
                    if result_row.get("significant"):
                        changes.append(result_row)
                        src  = listing.source.name if listing.source else "unknown"
                        old  = result_row["old_price"]
                        new  = result_row["new_price"]
                        pct  = result_row["change_pct"]
                        direction = result_row["direction"]
                        await log_event(
                            "PRICE CHANGE",
                            f"{prod_name} on {src}: EUR {old:.0f} -> {new:.0f} ({'+' if direction=='up' else '-'}{pct}%)",
                        )

                if progress_callback:
                    await progress_callback(
                        f"Checked: {listing.listing_title or listing.listing_url[:60]}"
                    )
                await asyncio.sleep(2)

            except Exception as e:
                log.error("Listing check failed", listing_id=str(listing.id), error=str(e))
                errors.append({"listing_id": str(listing.id), "error": str(e)})
                src = listing.source.slug if listing.source else "unknown"
                await log_event("SCRAPER FAIL", f"{src} | {prod_name}: {str(e)[:120]}")

        summary_msg = (
            f"{len(listings)} listings checked, "
            f"{len(changes)} significant changes, "
            f"{len(errors)} errors"
        )
        await log_event("PRICE CHECK END", summary_msg, run_id=run_id)
        log.info("Price check completed", run_id=run_id)

        return {
            "listings_checked": len(listings),
            "prices_updated": updated,
            "price_changes": changes,
            "errors": errors,
            "listings_discovered": discovery.get("discovered", 0),
        }

    async def _check_listing(self, listing: ProductListing, session: AsyncSession) -> dict | None:
        prev_result = await session.execute(
            select(PriceHistory)
            .where(PriceHistory.listing_id == listing.id)
            .order_by(desc(PriceHistory.scraped_at))
            .limit(1)
        )
        prev = prev_result.scalar_one_or_none()
        prev_price = prev.price_eur if prev else None

        source_slug = listing.source.slug if listing.source else None
        scraper = get_scraper(source_slug) if source_slug else None
        if not scraper:
            log.warning("No scraper for listing", url=listing.listing_url, source=source_slug)
            prod_name = listing.product.name if listing.product else listing.listing_title or "?"
            await log_event(
                "SCRAPER FAIL",
                f"{source_slug or 'unknown'} | {prod_name}: no scraper registered for this source",
            )
            return None

        scraped = await scraper.get_listing(listing.listing_url)

        if scraped.price_eur is None and scraped.error is None:
            scraped.error = "Scraper returned no price and no error — selector may be broken"
            prod_name = listing.product.name if listing.product else listing.listing_title or "?"
            await log_event(
                "SCRAPER FAIL",
                f"{source_slug} | {prod_name}: no price, no error — selector likely broken on {listing.listing_url}",
            )

        ph = PriceHistory(
            listing_id=listing.id,
            price_eur=scraped.price_eur,
            in_stock=scraped.in_stock,
            ships_to_germany=scraped.ships_to_germany,
            screenshot_path=scraped.screenshot_path,
            raw_data={},
            scraped_at=datetime.now(timezone.utc),
        )
        session.add(ph)

        listing.last_scraped_at = datetime.now(timezone.utc)
        if scraped.price_eur is not None:
            listing.last_verified_at = datetime.now(timezone.utc)
        listing.is_available = bool(scraped.in_stock)

        await session.flush()

        row = {
            "listing_id": str(listing.id),
            "product_id": str(listing.product_id),
            "ph_id": str(ph.id),
            "price_eur": scraped.price_eur,
            "source": listing.source.name if listing.source else "unknown",
            "source_slug": source_slug,
            "url": listing.listing_url,
            "title": listing.listing_title,
            "significant": False,
            "price_changed": False,
        }

        if prev_price and scraped.price_eur:
            change_pct = abs(scraped.price_eur - prev_price) / prev_price
            if change_pct >= PRICE_CHANGE_THRESHOLD:
                direction = "down" if scraped.price_eur < prev_price else "up"
                log.info("Price change detected", listing=listing.listing_title,
                         old=prev_price, new=scraped.price_eur, pct=f"{change_pct:.1%}")
                row.update({
                    "significant": True,
                    "price_changed": True,
                    "old_price": prev_price,
                    "new_price": scraped.price_eur,
                    "change_pct": round(change_pct * 100, 1),
                    "direction": direction,
                })
            else:
                row["price_changed"] = True

        return row
