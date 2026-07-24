"""
Seeds the database with initial data:
  - AI Hardware scope (128GB+ unified memory)
  - All 6 initial sources
  - Known products (DGX Spark, GMKtec EVO-X2, etc.)
  - Initial product listings

Run once after migrations: python -m backend.db.seed
"""

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select

from backend.db.models import (
    Product,
    ProductListing,
    ProductScope,
    ScopeSource,
    Source,
)
from backend.db.session import get_session


SOURCES = [
    {
        "name": "geizhals.de",
        "slug": "geizhals-de",
        "base_url": "https://geizhals.de",
        "scraper_type": "playwright",
        "rate_limit_seconds": 5.0,
        "config": {"search_path": "/?fs={query}&in=&fc=&w=-1&v=e&hloc=at&hloc=de"},
    },
    {
        "name": "amazon.de",
        "slug": "amazon-de",
        "base_url": "https://www.amazon.de",
        "scraper_type": "playwright",
        "rate_limit_seconds": 8.0,
        "config": {"search_path": "/s?k={query}"},
    },
    {
        "name": "GMKtec",
        "slug": "gmktec",
        "base_url": "https://de.gmktec.com/en",
        "scraper_type": "httpx",
        "rate_limit_seconds": 3.0,
        "config": {"skip_auto_discovery": True},
    },
    {
        "name": "Voelkner",
        "slug": "voelkner",
        "base_url": "https://www.voelkner.de",
        "scraper_type": "httpx",
        "rate_limit_seconds": 3.0,
        "config": {
            "search_path": "/search/?searchparam={query}&filter=category%3Dcomputers"
        },
    },
    {
        "name": "Galaxus",
        "slug": "galaxus-de",
        "base_url": "https://www.galaxus.de",
        "scraper_type": "playwright",
        "rate_limit_seconds": 5.0,
        "config": {"search_path": "/en/s1/producttype/pc-18?q={query}"},
    },
    {
        "name": "alternate.de",
        "slug": "alternate-de",
        "base_url": "https://www.alternate.de",
        "scraper_type": "httpx",
        "rate_limit_seconds": 4.0,
        "config": {"search_path": "/listing.xhtml?q={query}"},
    },
    {
        "name": "jacob.de",
        "slug": "jacob-de",
        "base_url": "https://www.jacob.de",
        "scraper_type": "httpx",
        "rate_limit_seconds": 4.0,
        "config": {"search_path": "/q/{query}"},
    },
    {
        "name": "ACEMAGIC DE",
        "slug": "acemagic-de",
        "base_url": "https://acemagic.de",
        "scraper_type": "httpx",
        "rate_limit_seconds": 3.0,
        "config": {"skip_auto_discovery": True},
    },
]

AI_HARDWARE_SCOPE = {
    "name": "AI Hardware",
    "slug": "ai-hardware",
    "description": (
        "Local computing hardware with 128GB+ unified memory, CPU and GPU on the same chip, "
        "capable of running large language models locally. Products must be purchasable in Germany."
    ),
    "qualifier_rules": {
        "min_unified_memory_gb": 128,
        "cpu_gpu_unified": True,
        "must_ship_to_germany": True,
        "description": (
            "Product qualifies if: unified memory >= 128GB, CPU and GPU share the same memory pool "
            "(no separate VRAM), capable of running 70B+ parameter LLMs, available to buy in Germany with EUR pricing."
        ),
        "disqualifiers": [
            "Discrete GPU (separate VRAM)",
            "Less than 128GB total memory",
            "Not available for shipping to Germany",
            "Server/rack unit not suitable for desktop use",
        ],
    },
    "search_terms": [
        "128GB unified memory mini PC",
        "NVIDIA DGX Spark",
        "AMD Ryzen AI Max 395 mini PC",
        "Strix Halo 128GB desktop",
        "GMKtec EVO-X2",
        "AMD Ryzen AI Max+ 395 128GB",
        "local AI workstation 128GB",
        "mini PC unified memory LLM",
    ],
    "min_price_eur": 800.0,
}

INITIAL_PRODUCTS = [
    {
        "name": "NVIDIA DGX Spark",
        "brand": "NVIDIA",
        "model": "DGX Spark (GB10)",
        "specs": {
            "chip": "Grace Blackwell GB10",
            "unified_memory_gb": 128,
            "memory_bandwidth_gbps": 273,
            "cpu_cores": 20,
            "gpu_model": "Blackwell GPU",
            "tdp_watts": 60,
            "form_factor": "mini PC",
            "os": "Linux (DGX OS)",
        },
        "notes": "NVIDIA's personal AI supercomputer. First released 2025.",
        "listings": [
            {
                "source_slug": "amazon-de",
                "url": "https://www.amazon.de/s?k=NVIDIA+DGX+Spark",
                "title": "NVIDIA DGX Spark on Amazon.de",
                "is_primary": False,
            }
        ],
    },
    {
        "name": "GMKtec EVO-X2 (128GB)",
        "brand": "GMKtec",
        "model": "EVO-X2",
        "specs": {
            "chip": "AMD Ryzen AI Max+ 395 (Strix Halo)",
            "unified_memory_gb": 128,
            "memory_bandwidth_gbps": 273,
            "cpu_cores": 16,
            "gpu_model": "Radeon 890M (RDNA 3.5, 40 CU)",
            "tdp_watts": 54,
            "form_factor": "mini PC",
            "os": "Windows 11",
        },
        "notes": "AMD Strix Halo mini PC. More affordable DGX Spark alternative.",
        "listings": [
            {
                "source_slug": "amazon-de",
                "url": "https://www.amazon.de/s?k=GMKtec+EVO-X2+128GB+Ryzen+AI+Max",
                "title": "GMKtec EVO-X2 on Amazon.de",
                "is_primary": True,
            },
        ],
    },
    {
        "name": "Minisforum MS-S1 Max (128GB)",
        "brand": "Minisforum",
        "model": "MS-S1 Max",
        "specs": {
            "chip": "AMD Ryzen AI Max+ 395 (Strix Halo)",
            "unified_memory_gb": 128,
            "memory_bandwidth_gbps": 273,
            "cpu_cores": 16,
            "gpu_model": "Radeon 890M (RDNA 3.5, 40 CU)",
            "tdp_watts": 54,
            "form_factor": "mini PC",
            "os": "Windows 11",
        },
        "notes": "Minisforum's Strix Halo mini PC with 128GB unified memory.",
        "listings": [
            {
                "source_slug": "amazon-de",
                "url": "https://www.amazon.de/s?k=Minisforum+MS-S1+Max+128GB",
                "title": "Minisforum MS-S1 Max on Amazon.de",
                "is_primary": False,
            }
        ],
    },
]

SCOPE_SOURCE_SEARCH_URLS = {
    "geizhals-de": "https://geizhals.de/?fs={query}&in=&fc=&w=-1&v=e&hloc=at&hloc=de",
    "amazon-de": "https://www.amazon.de/s?k={query}",
    "gmktec": "https://de.gmktec.com/en/search?q={query}",
    "voelkner": "https://www.voelkner.de/search/?searchparam={query}",
    "galaxus-de": "https://www.galaxus.de/en/s1/producttype/pc-18?q={query}",
    "alternate-de": "https://www.alternate.de/listing.xhtml?q={query}",
    "jacob-de": "https://www.jacob.de/q/{query}",
    "acemagic-de": "https://acemagic.de/search?q={query}&type=product",
}


async def seed():
    print("Seeding database...")

    async with get_session() as session:
        # --- Sources ---
        source_map: dict[str, Source] = {}
        for s_data in SOURCES:
            result = await session.execute(
                select(Source).where(Source.slug == s_data["slug"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                source = Source(**s_data)
                session.add(source)
                await session.flush()
                source_map[s_data["slug"]] = source
                print(f"  + Source: {s_data['name']}")
            else:
                source_map[s_data["slug"]] = existing
                print(f"  ~ Source already exists: {s_data['name']}")

        # --- AI Hardware Scope ---
        result = await session.execute(
            select(ProductScope).where(ProductScope.slug == AI_HARDWARE_SCOPE["slug"])
        )
        scope = result.scalar_one_or_none()
        if not scope:
            scope = ProductScope(**AI_HARDWARE_SCOPE)
            session.add(scope)
            await session.flush()
            print(f"  + Scope: {scope.name}")
        else:
            print(f"  ~ Scope already exists: {scope.name}")

        # --- Scope Sources (link all sources to AI Hardware scope) ---
        for slug, url_template in SCOPE_SOURCE_SEARCH_URLS.items():
            if slug not in source_map:
                continue
            result = await session.execute(
                select(ScopeSource).where(
                    ScopeSource.scope_id == scope.id,
                    ScopeSource.source_id == source_map[slug].id,
                )
            )
            existing = result.scalar_one_or_none()
            if not existing:
                ss = ScopeSource(
                    scope_id=scope.id,
                    source_id=source_map[slug].id,
                    search_url_template=url_template,
                )
                session.add(ss)
                print(f"  + Linked source '{slug}' to AI Hardware scope")

        # --- Initial Products ---
        for p_data in INITIAL_PRODUCTS:
            listings_data = p_data.pop("listings", [])
            result = await session.execute(
                select(Product).where(
                    Product.scope_id == scope.id, Product.name == p_data["name"]
                )
            )
            existing_product = result.scalar_one_or_none()
            if not existing_product:
                product = Product(scope_id=scope.id, **p_data)
                session.add(product)
                await session.flush()
                print(f"  + Product: {product.name}")

                for l_data in listings_data:
                    source_slug = l_data.pop("source_slug")
                    if source_slug in source_map:
                        listing = ProductListing(
                            product_id=product.id,
                            source_id=source_map[source_slug].id,
                            listing_url=l_data["url"],
                            listing_title=l_data.get("title"),
                            is_primary=l_data.get("is_primary", False),
                        )
                        session.add(listing)
            else:
                print(f"  ~ Product already exists: {p_data['name']}")

    print("Seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
