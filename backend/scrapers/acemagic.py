"""
Scraper for acemagic.de — manufacturer's German Shopify store.
Same structure as de.gmktec.com — httpx + BeautifulSoup.
"""

import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)


class AcemagicScraper(BaseHttpScraper):
    BASE_URL = "https://acemagic.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=3.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        soup = await self.get(f"{self.BASE_URL}/search?q={query.replace(' ', '+')}&type=product")
        if not soup:
            return []

        results = []
        for link in soup.select("a.product-card__title, a.product__title, .product-item a, a[href*='/products/']")[:max_results]:
            href = link.get("href", "")
            if "/products/" not in href:
                continue
            url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
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
            title_el = soup.select_one("h1.product__title, h1.product-single__title, h1")
            result.title = title_el.get_text(strip=True) if title_el else ""

            # Scope to <main> to exclude related-product carousels in the footer.
            # Prefer .price-item--sale (current price); fall back to .price-item--regular.
            main = soup.select_one("main") or soup
            price_el = (
                main.select_one(".price-item--sale")
                or main.select_one(".price-item--regular")
            )
            if price_el:
                result.price_eur = self._parse_price(price_el.get_text())

            sold_out = soup.select_one(".sold-out, [class*='sold-out'], [class*='soldout']")
            add_to_cart = soup.select_one("button[name='add'], .product-form__cart-submit")
            result.in_stock = bool(add_to_cart) and not bool(sold_out)
            result.ships_to_germany = True  # DE store
            result.error = None

        except Exception as e:
            result.error = str(e)
            log.error("Acemagic parse error", url=url, error=str(e))

        return result
