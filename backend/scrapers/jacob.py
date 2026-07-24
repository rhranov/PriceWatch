"""
Scraper for jacob.de — German B2B/B2C electronics dealer.
Uses httpx + BeautifulSoup (mostly static HTML).
"""

import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)

OUT_OF_STOCK = ["nicht lieferbar", "ausverkauft", "nicht verfügbar", "auf anfrage"]
IN_STOCK = ["sofort lieferbar", "auf lager", "lieferbar", "sofort verfügbar", "in stock"]


class JacobScraper(BaseHttpScraper):
    BASE_URL = "https://www.jacob.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=4.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        url = f"{self.BASE_URL}/q/{query.replace(' ', '+')}"
        soup = await self.get(url)
        results = []

        if not soup:
            return results

        # Card: div.c1_product__part--offer contains hidden form inputs with product data
        cards = soup.select("div.c1_product__part--offer")
        log.info("Jacob search", query=query, url=url, cards=len(cards))

        for card in cards[:max_results]:
            try:
                # Product name from hidden form input
                name_input = card.select_one("input[name='name']")
                title = name_input.get("value", "").strip() if name_input else ""
                if not title:
                    continue

                # Product URL from price link
                link_el = card.select_one("a.product_price_link")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                prod_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                # Price from the link text (e.g. "3.689,00€")
                price = self._parse_price(link_el.get_text(strip=True))

                if title and prod_url:
                    results.append(ScrapeResult(url=prod_url, title=title, price_eur=price))
            except Exception as e:
                log.debug("Jacob card error", error=str(e))

        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        soup = await self.get(url)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        if not soup:
            result.error = "Failed to fetch"
            return result

        try:
            # h1.c1_product__title no longer exists after site redesign — plain h1 works.
            title_el = soup.select_one("h1")
            result.title = title_el.get_text(strip=True) if title_el else ""

            # div.c1_price / div.productPrice__highlight no longer exist after site redesign.
            # Iterate all price-class elements and take the first that parses to a number.
            for el in soup.select("[class*='price']"):
                p = self._parse_price(el.get_text())
                if p is not None:
                    result.price_eur = p
                    break

            # Scope availability check to the dedicated availability element only.
            avail_el = soup.select_one("[class*='availability']")
            if avail_el:
                avail_text = avail_el.get_text(separator=" ", strip=True).lower()
            else:
                avail_text = soup.get_text().lower()
            result.in_stock = any(i in avail_text for i in IN_STOCK) and not any(
                i in avail_text for i in OUT_OF_STOCK
            )
            result.ships_to_germany = True
            result.error = None

            log.info("Jacob listing", title=result.title, price=result.price_eur, in_stock=result.in_stock)
        except Exception as e:
            result.error = str(e)

        return result
