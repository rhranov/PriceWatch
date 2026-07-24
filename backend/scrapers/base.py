"""
Base scraper class with rate limiting, stealth, and result types.
All source scrapers inherit from BaseScraper or BasePlaywrightScraper.
"""

import asyncio
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from backend.config import settings
from backend.security.url_policy import (
    bounded_httpx_get,
    guard_browser_context,
    hosts_for_base_url,
)

log = structlog.get_logger(__name__)


@dataclass
class ScrapeResult:
    """Represents a single product/listing found during a scrape."""

    url: str
    title: str
    price_eur: float | None = None
    original_price_eur: float | None = None
    in_stock: bool | None = None
    ships_to_germany: bool | None = None
    ships_from: str | None = None
    delivery_days_min: int | None = None
    delivery_days_max: int | None = None
    screenshot_path: str | None = None
    raw_html: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None

    @property
    def is_available(self) -> bool:
        return bool(self.in_stock and self.ships_to_germany and self.price_eur)


# ---------------------------------------------------------------------------
# HTTP-based scraper (for simpler/static sites)
# ---------------------------------------------------------------------------


class BaseHttpScraper(ABC):
    """Lightweight scraper using httpx + BeautifulSoup."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self, rate_limit_seconds: float = 4.0):
        self.rate_limit = rate_limit_seconds
        self._last_request: float = 0.0

    async def _wait(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        wait = random.uniform(self.rate_limit, self.rate_limit * 1.8)
        if elapsed < wait:
            await asyncio.sleep(wait - elapsed)
        self._last_request = asyncio.get_event_loop().time()

    async def get(self, url: str) -> BeautifulSoup | None:
        await self._wait()
        try:
            async with httpx.AsyncClient(headers=self.HEADERS, timeout=30.0) as client:
                response = await bounded_httpx_get(
                    client,
                    url,
                    allowed_hosts=hosts_for_base_url(self.BASE_URL),
                )
                if response.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}", request=None, response=None
                    )
                return BeautifulSoup(response.text, "lxml")
        except Exception as e:
            log.warning("HTTP scrape failed", url=url, error=str(e))
            return None

    @staticmethod
    def _parse_price(text: str) -> float | None:
        """Extract EUR price from arbitrary text like '1.234,56 €' or '€1234.56'."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d,.]", "", text.strip())
        if re.match(r"^\d{1,3}(\.\d{3})*,\d{2}$", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif re.match(r"^\d+,\d{2}$", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        ...

    @abstractmethod
    async def get_listing(self, url: str) -> ScrapeResult:
        ...


# ---------------------------------------------------------------------------
# Playwright-based scraper (for JS-heavy sites)
# ---------------------------------------------------------------------------

_BROWSER: Browser | None = None
_PLAYWRIGHT_CTX = None


async def get_browser() -> Browser:
    """Shared browser instance — call once, reuse across scrapers."""
    global _BROWSER, _PLAYWRIGHT_CTX
    if _BROWSER is None or not _BROWSER.is_connected():
        _PLAYWRIGHT_CTX = await async_playwright().start()
        _BROWSER = await _PLAYWRIGHT_CTX.chromium.launch(
            headless=settings.playwright_headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
    return _BROWSER


async def close_browser():
    global _BROWSER, _PLAYWRIGHT_CTX
    if _BROWSER:
        await _BROWSER.close()
        _BROWSER = None
    if _PLAYWRIGHT_CTX:
        await _PLAYWRIGHT_CTX.stop()
        _PLAYWRIGHT_CTX = None


class BasePlaywrightScraper(ABC):
    """Browser-based scraper for JS-heavy sites."""

    STEALTH_SCRIPT = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['de-DE','de','en-US','en']});
        window.chrome = {runtime: {}};
    """

    def __init__(self, rate_limit_seconds: float = 6.0):
        self.rate_limit = rate_limit_seconds
        self._last_request: float = 0.0

    async def _wait(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        wait = random.uniform(self.rate_limit, self.rate_limit * 1.6)
        if elapsed < wait:
            await asyncio.sleep(wait - elapsed)
        self._last_request = asyncio.get_event_loop().time()

    async def _new_context(self, browser: Browser) -> BrowserContext:
        ctx = await browser.new_context(
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "de-DE,de;q=0.9"},
        )
        await ctx.add_init_script(self.STEALTH_SCRIPT)
        await guard_browser_context(
            ctx, allowed_hosts=hosts_for_base_url(self.BASE_URL)
        )
        return ctx

    async def _screenshot(self, page: Page, name: str) -> str | None:
        try:
            path = settings.screenshot_dir / f"{name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception:
            return None

    @staticmethod
    def _parse_price(text: str) -> float | None:
        """Extract EUR price from arbitrary text like '1.234,56 €' or '€1234.56'."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d,.]", "", text.strip())
        # German format with thousands dot: 1.234,56
        if re.match(r"^\d{1,3}(\.\d{3})*,\d{2}$", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        # German format without thousands separator: 1999,96
        elif re.match(r"^\d+,\d{2}$", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[ScrapeResult]:
        ...

    @abstractmethod
    async def get_listing(self, url: str) -> ScrapeResult:
        ...
