"""
Single verification gateway for all URL acceptance paths.

Every entry point that writes a URL into product_listings or pending_discoveries
must call verify_listing_url() first and use the returned live data.
This prevents unverified, estimated, or hallucinated prices from entering the DB.
"""

import structlog

from backend.scrapers.registry import get_scraper
from backend.scrapers.base import BasePlaywrightScraper
from backend.security.product_identity import product_title_matches
from backend.security.url_policy import UnsafeUrlError, hosts_for_base_url, validate_url

log = structlog.get_logger(__name__)


async def verify_listing_url(
    source_slug: str,
    url: str,
    expected_product_name: str | None = None,
) -> tuple[bool, float | None, str, bool | None, str | None]:
    """
    Fetch url via the production scraper for source_slug.
    Returns (ok, price_eur, title, in_stock, error).

    ok=True  — scraper fetched the page, got a non-empty title.
               price_eur may still be None (product temporarily unavailable).
    ok=False — scraper failed, returned an error, or returned completely empty
               result (no title AND no price). Callers must reject the URL.

    For discovery submissions, callers must additionally check price_eur is not None.
    For listing additions, ok=True with non-empty title is sufficient.

    Uses fresh playwright per call so it works in both the backend process
    (ProactorEventLoop) and the integration subprocess (WindowsSelectorEventLoopPolicy).
    """
    scraper = get_scraper(source_slug)
    if scraper is None:
        return False, None, "", None, f"No scraper registered for '{source_slug}'"

    try:
        try:
            url = validate_url(url, allowed_hosts=hosts_for_base_url(scraper.BASE_URL))
        except UnsafeUrlError as exc:
            log.warning("verify_listing_url: unsafe destination", source=source_slug, error=str(exc))
            return False, None, "", None, f"Unsafe listing URL: {exc}"

        if isinstance(scraper, BasePlaywrightScraper):
            from playwright.async_api import async_playwright
            from backend.config import settings
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=settings.playwright_headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                try:
                    result = await scraper.get_listing(url, browser=browser)
                finally:
                    await browser.close()
        else:
            result = await scraper.get_listing(url)
    except Exception as exc:
        log.error("verify_listing_url: scraper raised exception", source=source_slug, url=url, error=str(exc))
        return False, None, "", None, f"Scraper raised exception: {exc}"

    if result.error:
        log.warning("verify_listing_url: scraper returned error", source=source_slug, url=url, error=result.error)
        return False, None, result.title or "", result.in_stock, result.error

    if not result.title:
        msg = "Scraper returned empty result (no title, no price) — page may require login, be unavailable, or block this scraper"
        log.warning("verify_listing_url: empty result", source=source_slug, url=url)
        return False, None, "", result.in_stock, msg

    if expected_product_name and not product_title_matches(expected_product_name, result.title):
        msg = "Final page title does not match the expected product"
        log.warning(
            "verify_listing_url: product identity mismatch",
            source=source_slug, expected=expected_product_name, actual=result.title[:100],
        )
        return False, None, result.title, result.in_stock, msg

        source=source_slug,
    log.info(
        "verify_listing_url: ok",
        url=url,
        title=result.title[:60] if result.title else "",
        price=result.price_eur,
        in_stock=result.in_stock,
    )
    return True, result.price_eur, result.title or "", result.in_stock, None
