"""
Scraper for reifendirekt.de — German tyre retailer (Delticom group).
Uses httpx + BeautifulSoup + regex (static HTML, no JS rendering needed).

Price pattern: "nur230,80€" — regex extracts the value after "nur".
Stock: [class*="lager"] elements contain "auf Lager" when in stock.
"""

import re
import structlog

from backend.scrapers.base import BaseHttpScraper, ScrapeResult

log = structlog.get_logger(__name__)

# Regex to extract selling price from "nur230,80€" or "nur 230,80 €"
_PRICE_RE = re.compile(r"nur\s*([\d]{1,4}[,\.]\d{2})\s*€", re.IGNORECASE)

OUT_OF_STOCK = ["nicht auf lager", "nicht lieferbar", "ausverkauft", "nicht verfügbar"]


class ReifendirektScraper(BaseHttpScraper):
    BASE_URL = "https://www.reifendirekt.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=3.0)

    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        # URL structure: /rshop/Winterreifen/{size}  or  /rshop/search/?q=...
        encoded = query.replace(" ", "+").replace("/", "%2F")
        url = f"{self.BASE_URL}/rshop/search/?q={encoded}"
        soup = await self.get(url)
        results = []
        if not soup:
            return results

        for card in soup.select("[class*='product'], [class*='artikel']")[:max_results]:
            try:
                link = card.select_one("a[href*='/rshop/Reifen/']")
                if not link:
                    continue
                prod_url = link.get("href", "")
                if not prod_url.startswith("http"):
                    prod_url = f"{self.BASE_URL}{prod_url}"

                title_el = card.select_one("h2, h3, [class*='name'], [class*='title']")
                title = title_el.get_text(separator=" ", strip=True) if title_el else ""

                text = card.get_text()
                m = _PRICE_RE.search(text)
                price = self._parse_price(m.group(1)) if m else None

                if prod_url and title:
                    results.append(ScrapeResult(url=prod_url, title=title, price_eur=price))
            except Exception as e:
                log.debug("ReifenDirekt search card error", error=str(e))

        return results

    async def get_listing(self, url: str) -> ScrapeResult:
        soup = await self.get(url)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        if not soup:
            result.error = "Failed to fetch"
            return result

        try:
            # Title from h1
            h1 = soup.select_one("h1")
            result.title = h1.get_text(separator=" ", strip=True) if h1 else ""

            # Price: regex on raw page text — "nur230,80€" pattern
            page_text = soup.get_text()
            m = _PRICE_RE.search(page_text)
            if m:
                result.price_eur = self._parse_price(m.group(1))

            # Stock: [class*="lager"] elements, or fall back to page text
            lager_els = soup.select("[class*='lager'], [class*='Lager']")
            if lager_els:
                lager_text = " ".join(el.get_text(strip=True).lower() for el in lager_els)
            else:
                lager_text = page_text.lower()

            result.in_stock = "auf lager" in lager_text and not any(
                phrase in lager_text for phrase in OUT_OF_STOCK
            )
            result.ships_to_germany = True
            result.error = None

            log.info(
                "ReifenDirekt listing",
                title=result.title,
                price=result.price_eur,
                in_stock=result.in_stock,
            )
        except Exception as e:
            result.error = str(e)
            log.error("ReifenDirekt get_listing error", url=url, error=str(e))

        return result
