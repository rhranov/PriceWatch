"""Fail-closed URL validation and bounded HTTP fetching."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 2_000_000


class UnsafeUrlError(ValueError):
    """Raised when a URL crosses the application's outbound network boundary."""


def _canonical_host(host: str) -> str:
    return host.rstrip(".").encode("idna").decode("ascii").lower()


def hosts_for_base_url(base_url: str, *extra_hosts: str) -> frozenset[str]:
    host = urlsplit(base_url).hostname
    if not host:
        raise ValueError(f"Base URL has no hostname: {base_url!r}")
    return frozenset({_canonical_host(host), *(_canonical_host(h) for h in extra_hosts)})


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return ip.is_global


def validate_url(
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    resolve: bool = True,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    """Validate a URL immediately before use and return its canonical form."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise UnsafeUrlError("URL must be a non-empty string of at most 2048 characters")

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Only http and https URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("Credentials in URLs are not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must include a hostname")

    host = _canonical_host(parsed.hostname)
    if allowed_hosts is not None:
        approved = {_canonical_host(item) for item in allowed_hosts}
        if host not in approved:
            raise UnsafeUrlError(f"Hostname {host!r} is not approved for this source")

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL contains an invalid port") from exc
    effective_port = port or (443 if scheme == "https" else 80)
    if effective_port not in ALLOWED_PORTS:
        raise UnsafeUrlError(f"Port {effective_port} is not allowed")

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
        if resolve:
            try:
                addresses = {
                    item[4][0]
                    for item in resolver(host, effective_port, type=socket.SOCK_STREAM)
                }
            except OSError as exc:
                raise UnsafeUrlError(f"Hostname could not be resolved: {host}") from exc
            if not addresses:
                raise UnsafeUrlError(f"Hostname could not be resolved: {host}")
            if any(not _is_public_ip(address) for address in addresses):
                raise UnsafeUrlError("Hostname resolves to a non-public address")
    else:
        if literal_ip.is_global:
            literal_ip = None
        else:
            raise UnsafeUrlError("Private, loopback, link-local, reserved, and unspecified addresses are blocked")

    netloc = host
    if port is not None:
        netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


@dataclass(frozen=True)
class BoundedResponse:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return self.content.decode(encoding, errors="replace")


async def bounded_httpx_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
) -> BoundedResponse:
    """GET with per-hop validation, manual redirects, and a decompressed byte cap."""
    current = url
    for redirect_count in range(max_redirects + 1):
        current = validate_url(current, allowed_hosts=allowed_hosts)
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise UnsafeUrlError("Redirect response has no Location header")
                if redirect_count >= max_redirects:
                    raise UnsafeUrlError("Too many redirects")
                current = urljoin(current, location)
                continue

            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise UnsafeUrlError("Response exceeds the configured byte limit")
                except ValueError:
                    raise UnsafeUrlError("Response has an invalid Content-Length header")

            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise UnsafeUrlError("Response exceeds the configured byte limit")
                chunks.append(chunk)
            return BoundedResponse(
                url=str(response.url),
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
            )
    raise UnsafeUrlError("Too many redirects")


async def guard_browser_context(context, *, allowed_hosts: Iterable[str]) -> None:
    """Apply destination checks to every browser request before connection."""

    async def route_guard(route, request):
        try:
            request_allowed_hosts = allowed_hosts if request.is_navigation_request() else None
            validate_url(request.url, allowed_hosts=request_allowed_hosts)
            if request.resource_type in {"media", "font", "websocket"}:
                await route.abort()
            else:
                await route.continue_()
        except (UnsafeUrlError, ValueError):
            await route.abort()

    await context.route("**/*", route_guard)


async def guard_browser_page(page, initial_url: str, *, allowed_hosts: Iterable[str] | None = None) -> str:
    """Validate the main navigation and block unsafe browser subrequests."""
    canonical = validate_url(initial_url, allowed_hosts=allowed_hosts)

    async def route_guard(route, request):
        try:
            request_allowed_hosts = allowed_hosts if request.is_navigation_request() else None
            validate_url(request.url, allowed_hosts=request_allowed_hosts)
            if request.resource_type in {"media", "font", "websocket"}:
                await route.abort()
            else:
                await route.continue_()
        except (UnsafeUrlError, ValueError):
            await route.abort()

    await page.route("**/*", route_guard)
    return canonical
