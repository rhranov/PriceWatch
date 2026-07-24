"""
Scraper for geizhals.de — Austrian/German price comparison.
search() uses Playwright (JS-rendered results).
get_listing() uses curl_cffi with browser impersonation to bypass Cloudflare Turnstile,
then reads offer rows that have a DE/AT country flag to avoid non-DE marketplace prices.

DO NOT use plain httpx or unassisted Playwright for get_listing:
- httpx: bypasses Cloudflare but hloc filter not applied server-side → gets global cheapest
- Playwright: Cloudflare Turnstile blocks JS → hloc filter never runs → same global cheapest
Both return prices from non-DE sellers (e.g. BA-Computer at ~€4,764 when DE floor is €5,961).
"""

import asyncio
import re as _re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import structlog

from backend.scrapers.base import BasePlaywrightScraper, ScrapeResult, get_browser
from backend.security.url_policy import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    UnsafeUrlError,
    hosts_for_base_url,
    validate_url,
)

log = structlog.get_logger(__name__)


class GeizhalsScraper(BasePlaywrightScraper):
    BASE_URL = "https://geizhals.de"
    LISTING_USES_PLAYWRIGHT = False  # get_listing uses curl_cffi, not Playwright

    def __init__(self):
        super().__init__(rate_limit_seconds=6.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        await self._wait()
        browser = await get_browser()
        ctx = await self._new_context(browser)
        results: list[ScrapeResult] = []

        try:
            page = await ctx.new_page()
            search_url = f"{self.BASE_URL}/?fs={query.replace(' ', '+')}&in=&fc=&w=-1&v=e&hloc=at&hloc=de"
            log.info("Geizhals search", url=search_url)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Cookie consent
            try:
                await page.click(".gh-cookie-btn--accept, button[data-testid='accept-all']", timeout=3000)
                await asyncio.sleep(1)
            except Exception:
                pass

            # Geizhals uses gallery view (as of 2026)
            cards = await page.query_selector_all("article")
            log.info("Geizhals found cards", count=len(cards))

            for card in cards[:max_results]:
                try:
                    title_el = await card.query_selector(".galleryview__name-link, h3 a")
                    title = (await title_el.inner_text()).strip() if title_el else ""
                    href = await title_el.get_attribute("href") if title_el else ""

                    price_el = await card.query_selector(".galleryview__price-link, .gh_price")
                    price_text = (await price_el.inner_text()).strip() if price_el else ""
                    price = self._parse_price(price_text)

                    url = href if href and href.startswith("http") else (f"{self.BASE_URL}{href}" if href else "")

                    if title and url:
                        results.append(ScrapeResult(url=url, title=title, price_eur=price))

                except Exception as e:
                    log.debug("Geizhals card error", error=str(e))

        except Exception as e:
            log.error("Geizhals search failed", query=query, error=str(e))
        finally:
            await ctx.close()

        return results

    async def get_listing(self, url: str, browser=None) -> ScrapeResult:  # browser unused — uses curl_cffi
        # curl_cffi with browser impersonation bypasses Cloudflare Turnstile.
        # We still add hloc=at&hloc=de — geizhals applies this server-side in the
        # HTML it returns, filtering the offer table to DE/AT sellers only.
        # We then require each offer row to have an explicit DE/AT flag element
        # (".gh-flag-DE" or ".gh-flag-AT") before accepting its price, preventing
        # non-DE marketplace rows from contaminating the result.
        url = validate_url(url, allowed_hosts=hosts_for_base_url(self.BASE_URL))
        parsed = urlsplit(url)
        query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "hloc"]
        query.extend((("hloc", "at"), ("hloc", "de")))
        url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), "")
        )

        await self._wait()
        result = ScrapeResult(url=url, title="", error="Not loaded")

        try:
            from curl_cffi.requests import AsyncSession
            from bs4 import BeautifulSoup

            async with AsyncSession() as session:
                current = url
                body = b""
                for redirect_count in range(MAX_REDIRECTS + 1):
                    current = validate_url(
                        current, allowed_hosts=hosts_for_base_url(self.BASE_URL)
                    )
                    chunks: list[bytes] = []
                    size = 0

                    def collect(chunk: bytes):
                        nonlocal size
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise UnsafeUrlError("Response exceeds the configured byte limit")
                        chunks.append(chunk)

                    resp = await session.get(
                        current,
                        impersonate="chrome120",
                        timeout=30,
                        allow_redirects=False,
                        content_callback=collect,
                    )
                    if resp.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count >= MAX_REDIRECTS:
                            raise UnsafeUrlError("Too many redirects")
                        current = urljoin(current, resp.headers.get("location", ""))
                        continue
                    body = b"".join(chunks)
                    break

            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}"
                return result

            soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "lxml")

            h1 = soup.select_one("h1")
            result.title = h1.get_text(strip=True) if h1 else ""

            # Offers are <div class="offer ..."> elements (NOT <tr>).
            # Each offer contains an <img alt="DE"> or <img alt="AT"> flag.
            # We only accept DE-flagged offers — AT shops are cheaper (different VAT)
            # but ship from Austria, not Germany.
            _PRICE_RE = _re.compile(r"\d+(?:\.\d{3})*,\d{2}")

            # Availability is judged per offer row, not page-wide: the cheapest
            # offer may be a pre-order ("Noch nicht verfügbar") while an in-stock
            # offer elsewhere on the page would otherwise mark the price in_stock.
            _UNAVAILABLE_MARKERS = (
                "noch nicht verfügbar",
                "nicht vorrätig",
                "nicht lagernd",
                "vorbestell",
            )

            de_available_price = None
            de_price = None

            for offer in soup.select("div.offer"):
                price_el = offer.select_one(".gh_price")
                if not price_el:
                    continue
                m = _PRICE_RE.search(price_el.get_text())
                if not m:
                    continue
                price = self._parse_price(m.group())
                if not price or price <= 0:
                    continue

                if offer.select_one('img[alt="DE"]'):
                    if de_price is None:
                        de_price = price
                    offer_text = offer.get_text(" ", strip=True).lower()
                    if not any(mk in offer_text for mk in _UNAVAILABLE_MARKERS):
                        de_available_price = price
                        break

            if de_available_price is not None:
                result.price_eur = de_available_price
                result.in_stock = True
            elif de_price is not None:
                log.warning(
                    "Geizhals get_listing: cheapest DE offer is not available (pre-order)",
                    url=url, price=de_price,
                )
                result.price_eur = de_price
                result.in_stock = False
            else:
                result.in_stock = False
            result.ships_to_germany = True
            result.error = None

        except Exception as e:
            result.error = str(e)
            log.error("Geizhals get_listing failed", url=url, error=str(e))

        return result
