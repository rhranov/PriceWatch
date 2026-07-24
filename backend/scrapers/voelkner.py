"""
Scraper for voelkner.de — German electronics retailer.
"""

import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)


class VoelknerScraper(BaseHttpScraper):
    BASE_URL = "https://www.voelkner.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=3.5)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        url = f"{self.BASE_URL}/search/search.html?keywords={query.replace(' ', '+')}"
        soup = await self.get(url)
        results = []

        if not soup:
            return results

        # Card: div.product_wrapper > div.product; link is the first <a> with a product URL
        cards = soup.select("div.product_wrapper")
        log.info("Voelkner found cards", count=len(cards))

        for card in cards[:max_results]:
            try:
                # Find the product link (full URL to /products/...)
                link_el = card.select_one("a[href*='/products/']")
                if not link_el:
                    continue
                prod_url = link_el.get("href", "")
                if not prod_url.startswith("http"):
                    prod_url = f"{self.BASE_URL}{prod_url}"
                title = link_el.get_text(strip=True)
                if not title:
                    title = link_el.get("title", "").strip()
                if not title:
                    continue

                price_el = card.select_one("div.product__price")
                price = self._parse_price(price_el.get_text()) if price_el else None

                results.append(ScrapeResult(url=prod_url, title=title, price_eur=price))

            except Exception as e:
                log.debug("Voelkner card error", error=str(e))

        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        soup = await self.get(url)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        if not soup:
            result.error = "Failed to fetch"
            return result

        try:
            title_el = soup.select_one("h1.product__title--pdp, h1")
            result.title = title_el.get_text(strip=True) if title_el else ""

            price_el = (
                soup.select_one("div.product__price--large")
                or soup.select_one("div.product__price")
                or soup.select_one("span.js_condition_offer_price")
            )
            if price_el:
                result.price_eur = self._parse_price(price_el.get_text())

            available_el = soup.select_one("span.product__availability__value--available")
            result.in_stock = bool(available_el)
            result.ships_to_germany = True
            result.error = None

        except Exception as e:
            result.error = str(e)

        return result
