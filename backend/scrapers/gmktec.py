"""
Scraper for de.gmktec.com — manufacturer's own store.
Uses httpx (simpler site structure).
"""

import asyncio
from datetime import datetime

import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)


class GmktecScraper(BaseHttpScraper):
    BASE_URL = "https://de.gmktec.com/en"

    def __init__(self):
        super().__init__(rate_limit_seconds=3.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        results = []
        soup = await self.get(f"{self.BASE_URL}/search?q={query.replace(' ', '+')}")
        if soup:
            product_links = soup.select("a.product-card__title, a.product__title, .product-item a")
            for link in product_links[:max_results]:
                href = link.get("href", "")
                if href and "/products/" in href:
                    url = f"https://de.gmktec.com{href}" if href.startswith("/") else href
                    title = link.get_text(strip=True)
                    if title:
                        results.append(ScrapeResult(url=url, title=title))
        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        soup = await self.get(url)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        if not soup:
            result.error = "Failed to fetch page"
            return result

        try:
            # Title
            title_el = soup.select_one("h1.product__title, h1.product-single__title, h1")
            result.title = title_el.get_text(strip=True) if title_el else ""

            # Price (GMKtec shows EUR on German store)
            price_el = soup.select_one(".product__price, .price, [class*='price']")
            if price_el:
                result.price_eur = self._parse_price(price_el.get_text())

            # Availability
            page_text = soup.get_text().lower()
            sold_out = soup.select_one(".sold-out, .product-form__soldout, [class*='sold']")
            add_to_cart = soup.select_one("button[name='add'], .product-form__cart-submit")

            result.in_stock = bool(add_to_cart) and not bool(sold_out)
            result.ships_to_germany = True  # DE store ships to Germany
            result.error = None

        except Exception as e:
            result.error = str(e)
            log.error("GMKtec parse error", url=url, error=str(e))

        return result
