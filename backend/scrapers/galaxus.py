"""
Scraper for galaxus.de.
Both search() and get_listing() use curl_cffi with browser impersonation.
Playwright fails with ERR_HTTP2_PROTOCOL_ERROR on all Galaxus pages.

search() parses __NEXT_DATA__ JSON that Next.js embeds in the page —
contains the full product list without needing JS execution.
get_listing() parses JSON-LD Product blocks for price and availability.
"""

import json
import re

import structlog

from backend.scrapers.base import BaseHttpScraper as BaseScraper, ScrapeResult

log = structlog.get_logger(__name__)


def _deep_get(d: dict, *keys):
    """Safely traverse nested dicts without raising."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _extract_galaxus_products(next_data: dict) -> list[dict]:
    """
    Walk __NEXT_DATA__ recursively to find the product list.
    Galaxus nests products under props.pageProps.searchResult or similar;
    we search for any list whose first element has both 'name' and 'id'.
    """
    found: list[dict] = []

    def walk(obj):
        if found:
            return
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict) and "name" in obj[0] and "id" in obj[0]:
                found.extend(obj)
                return
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    walk(next_data)
    return found


class GalaxusScraper(BaseScraper):
    BASE_URL = "https://www.galaxus.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=5.5)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        """
        Fetch Galaxus search results via curl_cffi and extract products from
        the __NEXT_DATA__ JSON blob that Next.js embeds in every page.
        Avoids Playwright entirely — works reliably with HTTP/2.
        """
        await self._wait()
        results: list[ScrapeResult] = []
        search_url = f"{self.BASE_URL}/en/s1/producttype/pc-18?q={query.replace(' ', '+')}"
        log.info("Galaxus search", url=search_url)

        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession() as session:
                resp = await session.get(search_url, impersonate="chrome120", timeout=30)

            if resp.status_code != 200:
                log.warning("Galaxus search bad status", status=resp.status_code, url=search_url)
                return results

            match = re.search(
                r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                resp.text,
                re.DOTALL,
            )
            if not match:
                log.warning("Galaxus search: __NEXT_DATA__ not found", url=search_url)
                return results

            data = json.loads(match.group(1))
            products = _extract_galaxus_products(data)
            log.info("Galaxus search: extracted products", count=len(products))

            for p in products[:max_results]:
                title = p.get("name") or p.get("title") or ""
                slug = p.get("slug") or p.get("nameUrlComponent") or ""
                product_id = p.get("id") or ""
                price_val = (
                    p.get("price")
                    or _deep_get(p, "offers", "price")
                    or _deep_get(p, "cheapestOffer", "price")
                )
                if slug and product_id:
                    url = f"{self.BASE_URL}/en/s1/product/{slug}-{product_id}"
                elif slug:
                    url = f"{self.BASE_URL}/en/s1/product/{slug}"
                else:
                    continue

                try:
                    price = float(price_val) if price_val is not None else None
                except (TypeError, ValueError):
                    price = None

                if title:
                    results.append(ScrapeResult(url=url, title=title, price_eur=price))

        except Exception as e:
            log.error("Galaxus search failed", query=query, error=str(e))

        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        # Playwright fails with ERR_HTTP2_PROTOCOL_ERROR on Galaxus product pages.
        # curl_cffi with browser impersonation works and returns JSON-LD with exact price.
        await self._wait()
        result = ScrapeResult(url=url, title="", error="Not loaded")

        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession() as session:
                resp = await session.get(url, impersonate="chrome120", timeout=30)

            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}"
                log.warning("Galaxus get_listing bad status", url=url, status=resp.status_code)
                return result

            ld_blocks = re.findall(
                r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
                resp.text,
                re.DOTALL,
            )

            for raw in ld_blocks:
                try:
                    data = json.loads(raw.strip())
                except Exception:
                    continue

                if data.get("@type") != "Product":
                    continue

                result.title = data.get("name", "")

                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}

                price_val = offers.get("price")
                if price_val is not None:
                    result.price_eur = float(price_val)

                avail = offers.get("availability", "")
                result.in_stock = "InStock" in avail
                result.ships_to_germany = True
                result.error = None
                break
            else:
                result.error = "No Product JSON-LD found on page"
                log.warning("Galaxus get_listing: no JSON-LD", url=url)

        except Exception as e:
            result.error = str(e)
            log.error("Galaxus get_listing failed", url=url, error=str(e))

        return result
