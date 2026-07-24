"""PriceWatch Model Context Protocol server.

The server exposes a deliberately narrow tool surface over the authenticated
loopback API. It never opens the database or reads application files directly.
Discovery approval and destructive operations remain human-only dashboard
actions and are not available as MCP tools.
"""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_API_URL = "http://127.0.0.1:8000"
ALLOWED_API_HOSTS = {"127.0.0.1", "localhost", "::1"}


class PriceWatchApiError(RuntimeError):
    """A bounded, credential-free API error suitable for an MCP client."""


def validate_api_url(value: str) -> str:
    """Require a plain loopback HTTP origin with no credentials or path."""
    parsed = urlsplit(value.strip())
    if parsed.scheme != "http":
        raise ValueError("PRICEWATCH_API_URL must use http on loopback")
    if parsed.hostname not in ALLOWED_API_HOSTS:
        raise ValueError("PRICEWATCH_API_URL must use a loopback host")
    if parsed.username or parsed.password:
        raise ValueError("PRICEWATCH_API_URL must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("PRICEWATCH_API_URL must be an origin without path, query, or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("PRICEWATCH_API_URL contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("PRICEWATCH_API_URL contains an invalid port")
    return value.strip().rstrip("/")


class PriceWatchApi:
    """Small authenticated client for the application API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = validate_api_url(base_url)
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("PRICEWATCH_API_KEY or API_KEY is required")
        self.transport = transport

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not path.startswith("/api/"):
            raise ValueError("MCP API paths must stay under /api/")
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key},
            follow_redirects=False,
            timeout=httpx.Timeout(20.0),
            transport=self.transport,
        ) as client:
            try:
                response = await client.request(method, path, params=params, json=json)
            except httpx.RequestError as exc:
                raise PriceWatchApiError(
                    f"PriceWatch API is unavailable at {self.base_url}"
                ) from exc

        if response.is_redirect:
            raise PriceWatchApiError("PriceWatch API returned an unexpected redirect")
        if response.is_error:
            detail = f"HTTP {response.status_code}"
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("detail"):
                    detail = f"{detail}: {str(body['detail'])[:300]}"
            except ValueError:
                pass
            raise PriceWatchApiError(detail)
        if response.status_code == 204 or not response.content:
            return {"status": "ok"}
        try:
            return response.json()
        except ValueError as exc:
            raise PriceWatchApiError("PriceWatch API returned invalid JSON") from exc


def get_api() -> PriceWatchApi:
    return PriceWatchApi(
        os.getenv("PRICEWATCH_API_URL", DEFAULT_API_URL),
        os.getenv("PRICEWATCH_API_KEY") or os.getenv("API_KEY", ""),
    )


mcp = FastMCP(
    "PriceWatch",
    instructions=(
        "Research products through PriceWatch's authenticated local API. "
        "Submitted discoveries remain pending until a human approves them."
    ),
)


@mcp.tool(description="Check whether the local PriceWatch API is available.")
async def pricewatch_health() -> dict[str, Any]:
    return await get_api().request("GET", "/api/health")


@mcp.tool(description="List configured product research scopes.")
async def list_scopes() -> list[dict[str, Any]]:
    return await get_api().request("GET", "/api/scopes")


@mcp.tool(description="List configured retailer sources.")
async def list_sources() -> list[dict[str, Any]]:
    return await get_api().request("GET", "/api/sources")


@mcp.tool(description="Inspect current scraper health for every retailer source.")
async def source_health() -> list[dict[str, Any]]:
    return await get_api().request("GET", "/api/sources/health")


@mcp.tool(description="List monitored products and their current retailer listings.")
async def list_products(
    scope_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    params = {key: value for key, value in {
        "scope_id": scope_id,
        "status": status,
    }.items() if value}
    return await get_api().request("GET", "/api/products", params=params)


@mcp.tool(description="List discoveries awaiting or previously receiving human review.")
async def list_discoveries(
    status: str = "pending",
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await get_api().request(
        "GET",
        "/api/discoveries",
        params={"status": status, "limit": max(1, min(limit, 200))},
    )


@mcp.tool(description="List recent PriceWatch agent and price-check runs.")
async def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return await get_api().request(
        "GET",
        "/api/runs",
        params={"limit": max(1, min(limit, 100))},
    )


@mcp.tool(
    description=(
        "Submit a retailer discovery. PriceWatch verifies the public listing URL "
        "and live product identity, then leaves the discovery pending for human review."
    )
)
async def submit_discovery(
    product_name: str,
    scope_slug: str,
    source_slug: str,
    listing_url: str,
    observed_price_eur: float,
    observed_in_stock: bool,
    brand: str | None = None,
    model: str | None = None,
    notes: str | None = None,
    confidence: Literal["high", "medium", "low"] = "medium",
) -> dict[str, Any]:
    return await get_api().request(
        "POST",
        "/api/discoveries/create",
        json={
            "product_name": product_name,
            "brand": brand,
            "model": model,
            "scope_slug": scope_slug,
            "source_slug": source_slug,
            "listing_url": listing_url,
            "price_eur": observed_price_eur,
            "in_stock": observed_in_stock,
            "notes": notes,
            "confidence": confidence,
        },
    )


@mcp.tool(description="Record an auditable market-research signal in the dashboard.")
async def record_research_signal(
    signal_type: str,
    title: str,
    significance: Literal["low", "medium", "high"] = "medium",
    summary: str | None = None,
    source_platform: str | None = None,
    source_url: str | None = None,
    scope_slug: str | None = None,
    action_required: bool = False,
    action_description: str | None = None,
    follow_up_date: str | None = None,
) -> dict[str, Any]:
    return await get_api().request(
        "POST",
        "/api/research/signals",
        json={
            "signal_type": signal_type,
            "significance": significance,
            "title": title,
            "summary": summary,
            "source_platform": source_platform,
            "source_url": source_url,
            "scope_slug": scope_slug,
            "action_required": action_required,
            "action_description": action_description,
            "follow_up_date": follow_up_date,
        },
    )


@mcp.tool(description="Register the beginning of an external agent research run.")
async def start_research_run(run_type: str = "deep_research") -> dict[str, Any]:
    return await get_api().request(
        "POST",
        "/api/runs/start",
        params={"run_type": run_type},
    )


@mcp.tool(description="Finish a registered research run and publish its summary.")
async def finish_research_run(
    run_id: str,
    status: Literal["completed", "completed_with_errors", "failed"] = "completed",
    discoveries_found: int = 0,
    products_checked: int = 0,
    prices_updated: int = 0,
    summary: str = "",
) -> dict[str, Any]:
    return await get_api().request(
        "POST",
        f"/api/runs/{run_id}/finish",
        json={
            "status": status,
            "discoveries_found": max(0, discoveries_found),
            "products_checked": max(0, products_checked),
            "prices_updated": max(0, prices_updated),
            "summary": summary,
        },
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
