"""
Import run-result JSON files produced by the scheduled Claude agent into Postgres.

For each run file the importer:
  * creates an agent_runs audit record
  * appends a price_history row per price update and updates the listing's
    last_scraped_at / last_verified_at / is_available
  * detects price changes >= 2% vs the previous record
  * creates pending_discoveries rows for new products the agent found

Idempotent: imported files are moved to data/sync/runs/processed/.

Format compatibility: handles both the canonical format and the older
"candidates" / "listing_url" / "new_price" / "available" field names.

Run manually:  python -m backend.sync.import_run [optional_path.json]
Or on a timer: scheduled every few minutes by backend/scheduler/jobs.py
"""

import asyncio
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from backend.db.models import (
    AgentRun,
    PendingDiscovery,
    PriceHistory,
    Product,
    ProductListing,
    ProductScope,
    ResearchSignal,
    ResearchWatch,
)
from backend.db.session import get_session

RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "sync" / "runs"
PROCESSED_DIR = RUNS_DIR / "processed"
QUARANTINE_DIR = RUNS_DIR / "quarantine"

CHANGE_THRESHOLD_PCT = 2.0
MAX_RUN_FILE_BYTES = 1_000_000
MAX_NESTING_DEPTH = 8
MAX_COLLECTION_ITEMS = 500
MAX_OBJECT_FIELDS = 100
MAX_STRING_LENGTH = 10_000


def _validate_value(value, depth: int = 0) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise ValueError("Run file exceeds the maximum nesting depth")
    if isinstance(value, dict):
        if len(value) > MAX_OBJECT_FIELDS:
            raise ValueError("Run file object has too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 100:
                raise ValueError("Run file contains an invalid object key")
            _validate_value(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("Run file collection has too many items")
        for item in value:
            _validate_value(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise ValueError("Run file string exceeds the maximum length")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Run file contains a non-finite number")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("Run file contains an unsupported value")


def _load_run_file(path: Path) -> tuple[dict, str]:
    if path.stat().st_size > MAX_RUN_FILE_BYTES:
        raise ValueError("Run file exceeds the 1 MB limit")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Run file root must be a JSON object")
    _validate_value(data)
    for field in ("price_updates", "discoveries", "research_signals", "errors", "data_checks"):
        if field in data and not isinstance(data[field], list):
            raise ValueError(f"{field} must be a JSON array")
    return data, digest



# Shops approved by the user that are not yet in the Sources table.
# Only the user may add to this list.
# alternate.de / cyberport.de / jacob.de are now in the Sources table and
# are picked up automatically by _get_approved_domains().
_USER_APPROVED_EXTRA_SHOPS: set[str] = set()


async def _get_approved_domains(session) -> set[str]:
    """
    Return the set of approved shop hostnames: active Sources table entries
    plus the user-approved extra shops above.
    Only the user may expand either list.
    """
    from urllib.parse import urlparse
    from backend.db.models import Source
    res = await session.execute(select(Source).where(Source.is_active == True))
    domains: set[str] = set(_USER_APPROVED_EXTRA_SHOPS)
    for src in res.scalars().all():
        host = urlparse(src.base_url).hostname
        if host:
            domains.add(host)
            if host.startswith("www."):
                domains.add(host[4:])
            else:
                domains.add(f"www.{host}")
    return domains


def _is_approved_source(url: str | None, approved_domains: set[str]) -> bool:
    """Return True only if url's hostname is in the approved Sources set."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return host in approved_domains
    except Exception:
        return False


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _adapt_run_data(data: dict) -> dict:
    """
    Normalize agent output format variations to the canonical import format.

    Deep Research agents may output 'candidates' instead of 'discoveries',
    and Daily Update agents may output 'listing_url'/'new_price'/'available'
    instead of 'listing_id'/'price_eur'/'in_stock'.
    """
    run_type = data.get("run_type", "daily")

    # Deep Research: candidates[] → discoveries[]
    if "candidates" in data and "discoveries" not in data:
        discoveries = []
        for c in data.get("candidates", []):
            discoveries.append({
                "scope_slug": c.get("scope_slug"),
                "name": c.get("name", "Unknown"),
                "brand": c.get("brand"),
                "model": c.get("model"),
                "specs": c.get("specs", {}),
                "source_name": c.get("source_name"),
                "source_url": c.get("url") or c.get("source_url"),
                "price_eur": c.get("price_eur"),
                "in_stock": c.get("in_stock", c.get("available_in_de")),
                "ships_to_germany": c.get("ships_to_germany", c.get("available_in_de")),
                "ai_reasoning": c.get("reasoning") or c.get("ai_reasoning"),
            })
        data = {**data, "discoveries": discoveries}

    # Daily Update: adapt price_update field name aliases
    if "price_updates" in data:
        adapted = []
        for upd in data["price_updates"]:
            adapted.append({
                **upd,
                # listing_url kept alongside; lookup done at import time
                "price_eur": upd.get("price_eur") or upd.get("new_price"),
                "in_stock": upd.get("in_stock") if upd.get("in_stock") is not None else upd.get("available"),
                "ships_to_germany": upd.get("ships_to_germany"),
            })
        data = {**data, "price_updates": adapted}

    return data


async def import_run_file(path: Path) -> str:
    data, source_digest = _load_run_file(path)
    data = _adapt_run_data(data)

    async with get_session() as session:
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS imported_run_claims (
                content_sha256 varchar(64) PRIMARY KEY,
                source_name varchar(255) NOT NULL,
                imported_at timestamptz NOT NULL DEFAULT NOW()
            )
        """))
        claimed = await session.execute(
            text("""
                INSERT INTO imported_run_claims (content_sha256, source_name)
                VALUES (:digest, :source_name)
                ON CONFLICT (content_sha256) DO NOTHING
                RETURNING content_sha256
            """),
            {"digest": source_digest, "source_name": path.name[:255]},
        )
        if claimed.scalar_one_or_none() is None:
            return f"{path.name}: already imported (content hash matched)"

        now = datetime.now(timezone.utc)
        approved_domains = await _get_approved_domains(session)
        run = AgentRun(
            run_type=data.get("run_type", "daily"),
            started_at=_parse_dt(data.get("started_at")) or _parse_dt(data.get("timestamp")) or now,
            finished_at=_parse_dt(data.get("finished_at")) or now,
            status="completed",
            scopes_checked=data.get("scopes_checked", []),
            errors=list(data.get("errors", [])),
            data_checks=list(data.get("data_checks", [])),
            tokens_used=data.get("tokens_used", {}),
            log_text=data.get("summary") or data.get("notes"),
        )
        session.add(run)
        await session.flush()

        errors = list(run.errors)
        price_changes: list[dict] = []
        prices_updated = 0
        checked_listings: set = set()

        for upd in data.get("price_updates", []):
            listing_id = upd.get("listing_id")

            # Fallback: look up listing by URL if no ID provided
            if not listing_id and upd.get("listing_url"):
                res_l = await session.execute(
                    select(ProductListing).where(
                        ProductListing.listing_url == upd["listing_url"]
                    )
                )
                found = res_l.scalar_one_or_none()
                listing_id = str(found.id) if found else None

            if not listing_id:
                errors.append({
                    "stage": "import",
                    "message": f"Cannot resolve listing: {upd.get('listing_url') or upd.get('listing_id')}",
                })
                continue

            res = await session.execute(
                select(ProductListing).where(ProductListing.id == listing_id)
            )
            listing = res.scalar_one_or_none()
            if not listing:
                errors.append(
                    {"stage": "import", "message": f"Unknown listing_id {listing_id}"}
                )
                continue

            # Previous price for change detection
            res_prev = await session.execute(
                select(PriceHistory)
                .where(PriceHistory.listing_id == listing.id)
                .order_by(PriceHistory.scraped_at.desc())
                .limit(1)
            )
            prev = res_prev.scalar_one_or_none()

            new_price = upd.get("price_eur")

            session.add(
                PriceHistory(
                    listing_id=listing.id,
                    price_eur=upd.get("price_eur"),
                    original_price_eur=upd.get("original_price_eur"),
                    in_stock=upd.get("in_stock"),
                    ships_to_germany=upd.get("ships_to_germany"),
                    ships_from=upd.get("ships_from"),
                    delivery_days_min=upd.get("delivery_days_min"),
                    delivery_days_max=upd.get("delivery_days_max"),
                    screenshot_path=upd.get("screenshot_path"),
                    raw_data=upd.get("raw_data", {}),
                )
            )
            prices_updated += 1
            checked_listings.add(listing.id)

            listing.last_scraped_at = now
            if upd.get("in_stock") is not None:
                listing.is_available = upd.get("in_stock")

            old_price = prev.price_eur if prev else None
            if new_price is not None and old_price not in (None, 0):
                pct = (new_price - old_price) / old_price * 100
                if abs(pct) >= CHANGE_THRESHOLD_PCT:
                    res_p = await session.execute(
                        select(Product).where(Product.id == listing.product_id)
                    )
                    prod = res_p.scalar_one_or_none()
                    price_changes.append(
                        {
                            "listing_id": str(listing.id),
                            "product_name": prod.name if prod else None,
                            "old_price": old_price,
                            "new_price": new_price,
                            "pct_change": round(pct, 2),
                        }
                    )

        discoveries_found = 0
        for disc in data.get("discoveries", []):
            # Normalise alternate field names agents sometimes emit
            name = disc.get("name") or disc.get("product_name") or "Unknown"
            brand = disc.get("brand") or disc.get("manufacturer")
            in_stock = (
                disc.get("in_stock")
                if disc.get("in_stock") is not None
                else disc.get("available_de")
                if disc.get("available_de") is not None
                else disc.get("available")
            )
            ships_to_germany = (
                disc.get("ships_to_germany")
                if disc.get("ships_to_germany") is not None
                else disc.get("available_de")
            )
            source_name = disc.get("source_name") or disc.get("source")
            # Build specs from dedicated fields if no specs dict provided
            specs = disc.get("specs") or {}
            if not specs:
                for key in ("memory_gb", "cpu", "gpu", "storage", "form_factor",
                            "memory_type", "vram_gb", "price_usd"):
                    if disc.get(key) is not None:
                        specs[key] = disc[key]
            ai_reasoning = disc.get("ai_reasoning") or disc.get("notes") or disc.get("qualification_notes")

            # Gate: source_url must be a confirmed shop, not a news article.
            # Discoveries exist to tell the user "you can buy this here at this price."
            # A news article cannot confirm that — it belongs in research_signals instead.
            source_url = disc.get("source_url")
            listing_url = disc.get("listing_url")
            confirmed_url = source_url if _is_approved_source(source_url, approved_domains) else (
                listing_url if _is_approved_source(listing_url, approved_domains) else None
            )
            if not confirmed_url:
                errors.append({
                    "stage": "import",
                    "message": (
                        f"Discovery '{name}' skipped — source_url '{source_url}' is not an "
                        f"approved shop (news articles do not confirm German availability or EUR price). "
                        f"Add a listing URL from an approved shop to qualify. "
                        f"Approved: {', '.join(sorted(approved_domains))}"
                    ),
                })
                continue

            scope_slug = disc.get("scope_slug")
            res_s = await session.execute(
                select(ProductScope).where(ProductScope.slug == scope_slug)
            )
            scope = res_s.scalar_one_or_none()
            if not scope:
                errors.append(
                    {"stage": "import", "message": f"Unknown scope_slug {scope_slug}"}
                )
                continue
            session.add(
                PendingDiscovery(
                    scope_id=scope.id,
                    name=name,
                    brand=brand,
                    model=disc.get("model"),
                    specs=specs,
                    source_name=source_name,
                    source_url=disc.get("source_url"),
                    price_eur=disc.get("price_eur"),
                    in_stock=in_stock,
                    ships_to_germany=ships_to_germany,
                    ai_reasoning=ai_reasoning,
                    screenshot_path=disc.get("screenshot_path"),
                    status="pending",
                    agent_run_id=run.id,
                )
            )
            discoveries_found += 1

        # Import research signals
        signals_imported = 0
        for sig_data in data.get("research_signals", []):
            sig = ResearchSignal(
                run_id=run.id,
                signal_type=sig_data.get("signal_type", "market_trend"),
                significance=sig_data.get("significance", "medium"),
                title=sig_data.get("title", "Untitled"),
                summary=sig_data.get("summary"),
                source_platform=sig_data.get("source_platform"),
                source_url=sig_data.get("source_url"),
                source_author=sig_data.get("source_author"),
                scope_slug=sig_data.get("scope_slug"),
                action_required=sig_data.get("action_required", False),
                action_description=sig_data.get("action_description"),
                follow_up_date=sig_data.get("follow_up_date"),
                status="new",
                notes=sig_data.get("notes"),
                raw_data=sig_data.get("raw_data", {}),
            )
            # Link to a product if product_id is provided
            if sig_data.get("product_id"):
                sig.product_id = sig_data["product_id"]
            session.add(sig)
            await session.flush()

            for w_data in sig_data.get("watches", []):
                session.add(ResearchWatch(
                    signal_id=sig.id,
                    watch_type=w_data.get("watch_type", "search_news"),
                    title=w_data.get("title", "Watch"),
                    description=w_data.get("description"),
                    target_url=w_data.get("target_url"),
                    search_query=w_data.get("search_query"),
                    check_by_date=w_data.get("check_by_date"),
                ))

            signals_imported += 1

        run.errors = errors
        run.status = "completed_with_errors" if errors else "completed"
        run.products_checked = len(checked_listings)
        run.prices_updated = prices_updated
        run.price_changes = price_changes
        run.discoveries_found = discoveries_found

    return (
        f"{path.name}: {prices_updated} price update(s), "
        f"{len(price_changes)} change(s) >= {CHANGE_THRESHOLD_PCT}%, "
        f"{discoveries_found} discovery(ies), "
        f"{signals_imported} research signal(s)"
    )


async def main():
    if len(sys.argv) > 1:
        paths = [Path(sys.argv[1])]
    else:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        paths = sorted(RUNS_DIR.glob("*.json"))

    if not paths:
        print("No run files to import.")
        return

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        try:
            print("Imported", await import_run_file(path))
            path.rename(PROCESSED_DIR / path.name)
        except Exception as exc:
            print(f"ERROR importing {path.name}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
