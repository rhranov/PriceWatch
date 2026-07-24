"""
Scraper for reifen.com — German tyre retailer (reifencom GmbH, Hannover).
Uses httpx + BeautifulSoup (static HTML).

Price: first non-empty [class*="product-price"] element matching EUR format.
Stock: presence of "Liefertermin" or "In den Warenkorb" button in delivery section.
"""

import re
import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)

_PRICE_RE = re.compile(r"([\d]{1,5}[,\.]\d{2})[\s\xa0]*€", re.UNICODE)


class ReifenComScraper(BaseHttpScraper):
    BASE_URL = "https://www.reifen.com/de-de"

    def __init__(self):
        super().__init__(rate_limit_seconds=3.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        # reifen.com search endpoint
        encoded = query.replace(" ", "+")
        url = f"{self.BASE_URL}/suche/{encoded}"
        soup = await self.get(url)
        results = []
        if not soup:
            return results

        for card in soup.select("[class*='product-card'], [class*='ProductCard'], article")[:max_results]:
            try:
                link = card.select_one("a[href]")
                if not link:
                    continue
                prod_url = link.get("href", "")
                if not prod_url.startswith("http"):
                    prod_url = f"https://www.reifen.com{prod_url}"

                title_el = card.select_one("h2, h3, [class*='product-name'], [class*='ProductName']")
                title = title_el.get_text(separator=" ", strip=True) if title_el else ""

                price_el = card.select_one("[class*='price'], [class*='Price']")
                price = None
                if price_el:
                    m = _PRICE_RE.search(price_el.get_text())
                    price = self._parse_price(m.group(1)) if m else None

                if prod_url and title:
                    results.append(ScrapeResult(url=prod_url, title=title, price_eur=price))
            except Exception as e:
                log.debug("Reifen.com search card error", error=str(e))

        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        soup = await self.get(url)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        if not soup:
            result.error = "Failed to fetch"
            return result

        try:
            # Title
            h1 = soup.select_one("h1")
            result.title = h1.get_text(separator=" ", strip=True) if h1 else ""

            # Price: try CSS selector first, then fall back to page-wide regex
            for el in soup.select("[class*='price'], [class*='Price']"):
                text = el.get_text(separator=" ", strip=True)
                m = _PRICE_RE.search(text)
                if m:
                    result.price_eur = self._parse_price(m.group(1))
                    break
            if result.price_eur is None:
                # Fallback: scan raw page text for the first plausible tyre price
                # (tyres are €50–€500/unit; skip quantity/service amounts near 0)
                for m in _PRICE_RE.finditer(soup.get_text(separator=" ")):
                    val = self._parse_price(m.group(1))
                    if val and 50 <= val <= 600:
                        result.price_eur = val
                        break

            # Stock: delivery section present + no "nicht lieferbar"
            page_text = soup.get_text().lower()
            delivery_el = soup.select_one("[class*='delivery'], [class*='Delivery']")
            delivery_text = delivery_el.get_text(strip=True).lower() if delivery_el else ""

            in_stock_signals = ["liefertermin", "in den warenkorb", "auf lager", "lieferbar"]
            out_of_stock_signals = ["nicht lieferbar", "ausverkauft", "nicht verfügbar", "nicht auf lager"]

            result.in_stock = (
                any(s in delivery_text or s in page_text for s in in_stock_signals)
                and not any(s in page_text for s in out_of_stock_signals)
            )
            result.ships_to_germany = True
            result.error = None

            log.info(
                "Reifen.com listing",
                title=result.title,
                price=result.price_eur,
                in_stock=result.in_stock,
            )
        except Exception as e:
            result.error = str(e)
            log.error("Reifen.com get_listing error", url=url, error=str(e))

        return result
