"""
Scraper for alternate.de — German online electronics retailer.
Uses httpx + BeautifulSoup (mostly static HTML).
"""

import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)

OUT_OF_STOCK = ["nicht lieferbar", "nicht verfügbar", "ausverkauft", "out of stock"]
IN_STOCK = ["sofort lieferbar", "auf lager", "lieferbar", "in stock", "sofort ab lager"]


class AlternateScraper(BaseHttpScraper):
    BASE_URL = "https://www.alternate.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=4.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        url = f"{self.BASE_URL}/listing.xhtml?q={query.replace(' ', '+')}"
        soup = await self.get(url)
        results = []

        if not soup:
            return results

        # Each card is <a class="...productBox..." href="..."> — the <a> IS the card and link
        cards = soup.select("a[class*='productBox']")
        log.info("Alternate search", query=query, url=url, cards=len(cards))

        for card in cards[:max_results]:
            try:
                prod_url = card.get("href", "")
                if not prod_url:
                    continue
                if not prod_url.startswith("http"):
                    prod_url = f"{self.BASE_URL}{prod_url}"

                name_el = card.select_one("div.product-name")
                title = name_el.get_text(separator=" ", strip=True) if name_el else ""
                if not title:
                    continue

                price_el = card.select_one("span.price")
                price = self._parse_price(price_el.get_text()) if price_el else None

                if title and prod_url:
                    results.append(ScrapeResult(url=prod_url, title=title, price_eur=price))
            except Exception as e:
                log.debug("Alternate card error", error=str(e))

        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        soup = await self.get(url)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        if not soup:
            result.error = "Failed to fetch"
            return result

        try:
            title_el = soup.select_one("h1, [class*='productTitle'], [itemprop='name']")
            result.title = title_el.get_text(separator=" ", strip=True) if title_el else ""

            price_el = soup.select_one(
                ".price.selling, .price-selling, [class*='price'][class*='selling'], "
                "[itemprop='price'], .price"
            )
            if price_el:
                result.price_eur = self._parse_price(
                    price_el.get("content") or price_el.get_text()
                )

            # Scope availability check to the product availability element only.
            # Page-wide text search causes false positives from banners and related products.
            avail_el = (
                soup.select_one("[class*='availability'], [class*='deliveryInfo'], [class*='stock']")
                or soup.select_one("[itemprop='availability']")
            )
            if avail_el:
                avail_text = avail_el.get_text(separator=" ", strip=True).lower()
            else:
                # Fall back to page text only when no dedicated element found
                avail_text = soup.get_text().lower()
            result.in_stock = any(i in avail_text for i in IN_STOCK) and not any(
                i in avail_text for i in OUT_OF_STOCK
            )
            result.ships_to_germany = True  # alternate.de ships within Germany
            result.error = None

            log.info("Alternate listing", title=result.title, price=result.price_eur, in_stock=result.in_stock)
        except Exception as e:
            result.error = str(e)

        return result
