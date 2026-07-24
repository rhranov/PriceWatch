"""
Scraper for amazon.de — requires stealth Playwright to avoid bot detection.
"""

import asyncio
import re
from datetime import datetime

import structlog

from backend.scrapers.base import BasePlaywrightScraper, ScrapeResult, get_browser

log = structlog.get_logger(__name__)


class AmazonDeScraper(BasePlaywrightScraper):
    BASE_URL = "https://www.amazon.de"

    def __init__(self):
        super().__init__(rate_limit_seconds=9.0)  # Amazon is strict

    async def search(self, query: str, max_results: int = 8) -> list[ScrapeResult]:
        await self._wait()
        browser = await get_browser()
        ctx = await self._new_context(browser)
        results: list[ScrapeResult] = []

        try:
            page = await ctx.new_page()
            search_url = f"{self.BASE_URL}/s?k={query.replace(' ', '+')}&l=de_DE"
            log.info("Amazon.de search", url=search_url)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(3)

            # Handle cookie consent
            try:
                await page.click("#sp-cc-accept", timeout=4000)
                await asyncio.sleep(1)
            except Exception:
                pass

            # Product cards
            cards = await page.query_selector_all("[data-component-type='s-search-result']")
            log.info("Amazon.de found cards", count=len(cards))

            for card in cards[:max_results]:
                try:
                    title_el = await card.query_selector("h2 span, h2 a span")
                    title = (await title_el.inner_text()).strip() if title_el else ""

                    price_whole = await card.query_selector(".a-price-whole")
                    price_frac = await card.query_selector(".a-price-fraction")
                    if price_whole:
                        whole = (await price_whole.inner_text()).strip().replace(".", "").replace(",", "")
                        frac = (await price_frac.inner_text()).strip() if price_frac else "00"
                        try:
                            price = float(f"{whole}.{frac}")
                        except ValueError:
                            price = None
                    else:
                        price = None

                    # Amazon puts data-asin on the card — use it for the canonical URL
                    asin = await card.get_attribute("data-asin")
                    if asin:
                        url = f"{self.BASE_URL}/dp/{asin}"
                    else:
                        # Fall back to extracting ASIN from any product link in the card
                        link_el = await card.query_selector("a[href*='/dp/']")
                        href = await link_el.get_attribute("href") if link_el else ""
                        asin_match = re.search(r"/dp/([A-Z0-9]{10})", href or "")
                        url = f"{self.BASE_URL}/dp/{asin_match.group(1)}" if asin_match else ""

                    if title and url:
                        results.append(ScrapeResult(url=url, title=title, price_eur=price))

                except Exception as e:
                    log.debug("Amazon card parse error", error=str(e))

        except Exception as e:
            log.error("Amazon.de search failed", query=query, error=str(e))
        finally:
            await ctx.close()

        return results

    async def get_listing(self, url: str, browser=None) -> ScrapeResult:
        await self._wait()
        _browser = browser if browser is not None else await get_browser()
        ctx = await self._new_context(_browser)
        result = ScrapeResult(url=url, title="", error="Not loaded")

        try:
            page = await ctx.new_page()
            log.info("Amazon.de get_listing", url=url)
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(3)

            try:
                await page.click("#sp-cc-accept", timeout=4000)
                await asyncio.sleep(1)
            except Exception:
                pass

            # Title
            title_el = await page.query_selector("#productTitle")
            result.title = (await title_el.inner_text()).strip() if title_el else ""

            # Price — only read from the buy box area, never from recommendation carousels.
            # Querying ".a-price .a-offscreen" page-wide picks up carousel prices when
            # the actual product has no active seller (as happened with ASUS Ascent GX10).
            price_el = await page.query_selector(
                "#corePriceDisplay_desktop_feature_div .a-offscreen, "
                "#corePrice_feature_div .a-offscreen, "
                "#price_inside_buybox, "
                "#apex_desktop .a-offscreen"
            )
            if price_el:
                result.price_eur = self._parse_price(await price_el.inner_text())

            # Availability
            avail_el = await page.query_selector("#availability span, #add-to-cart-button")
            avail_text = (await avail_el.inner_text()).strip().lower() if avail_el else ""
            add_to_cart = await page.query_selector("#add-to-cart-button")

            result.in_stock = bool(add_to_cart) and "nicht" not in avail_text and "unavailable" not in avail_text
            result.ships_to_germany = True  # amazon.de is Germany-specific

            # Check for German shipping
            deliver_el = await page.query_selector("#delivery-message, #mir-layout-DELIVERY_BLOCK")
            if deliver_el:
                deliver_text = (await deliver_el.inner_text()).lower()
                if "nicht lieferbar" in deliver_text or "not available" in deliver_text:
                    result.ships_to_germany = False
                    result.in_stock = False

            result.screenshot_path = await self._screenshot(page, f"amazon_{url.split('/')[-1][:20]}")
            result.error = None

        except Exception as e:
            result.error = str(e)
            log.error("Amazon.de get_listing failed", url=url, error=str(e))
        finally:
            await ctx.close()

        return result
