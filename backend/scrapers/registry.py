"""
Registry mapping source slugs to scraper instances.
Import get_scraper() everywhere instead of instantiating directly.
"""

from backend.scrapers.base import BaseHttpScraper, BasePlaywrightScraper
from backend.scrapers.geizhals import GeizhalsScraper
from backend.scrapers.amazon_de import AmazonDeScraper
from backend.scrapers.gmktec import GmktecScraper
from backend.scrapers.voelkner import VoelknerScraper
from backend.scrapers.galaxus import GalaxusScraper
from backend.scrapers.alternate import AlternateScraper
from backend.scrapers.jacob import JacobScraper
from backend.scrapers.acemagic import AcemagicScraper
from backend.scrapers.reifendirekt import ReifendirektScraper
from backend.scrapers.reifen_com import ReifenComScraper

_REGISTRY: dict[str, type] = {
    "geizhals-de": GeizhalsScraper,
    "amazon-de": AmazonDeScraper,
    "gmktec": GmktecScraper,
    "voelkner": VoelknerScraper,
    "galaxus-de": GalaxusScraper,
    "alternate-de": AlternateScraper,
    "jacob-de": JacobScraper,
    "acemagic-de": AcemagicScraper,
    "reifendirekt-de": ReifendirektScraper,
    "reifen-com": ReifenComScraper,
}

# Cached instances (one per source)
_INSTANCES: dict[str, BaseHttpScraper | BasePlaywrightScraper] = {}


def get_scraper(source_slug: str) -> BaseHttpScraper | BasePlaywrightScraper | None:
    """Return (and cache) a scraper instance for the given source slug."""
    if source_slug not in _REGISTRY:
        return None
    if source_slug not in _INSTANCES:
        _INSTANCES[source_slug] = _REGISTRY[source_slug]()
    return _INSTANCES[source_slug]
