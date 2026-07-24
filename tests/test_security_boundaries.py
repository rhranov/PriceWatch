from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("API_KEY", "test-api-key-that-is-long-enough-123456")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pricewatch:test-only@localhost/pricewatch")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://pricewatch:test-only@localhost/pricewatch")

from fastapi.testclient import TestClient
from backend.api.main import app
from backend.security.confirmations import (
    ConfirmationError,
    consume_confirmation,
    issue_confirmation,
)
from backend.scrapers.base import ScrapeResult
from backend.security.product_identity import product_title_matches
from backend.security.url_policy import UnsafeUrlError, validate_url


def public_resolver(*_args, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


class HostHeaderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rejects_untrusted_host_before_redirect_routing(self):
        response = self.client.get(
            "/api/products/",
            headers={
                "Host": "attacker.invalid",
                "X-API-Key": os.environ["API_KEY"],
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("location", response.headers)

    def test_rejects_untrusted_host_on_public_route(self):
        response = self.client.get(
            "/api/health",
            headers={"Host": "attacker.invalid"},
        )
        self.assertEqual(response.status_code, 400)

    def test_accepts_loopback_host_with_port(self):
        response = self.client.get(
            "/api/health",
            headers={"Host": "127.0.0.1:8000"},
        )
        self.assertEqual(response.status_code, 200)


class UrlPolicyTests(unittest.TestCase):
    def test_accepts_approved_public_https_url(self):
        result = validate_url(
            "https://shop.example/product/1",
            allowed_hosts={"shop.example"},
            resolver=public_resolver,
        )
        self.assertEqual(result, "https://shop.example/product/1")

    def test_rejects_local_and_browser_only_schemes(self):
        for url in (
            "file:///etc/passwd",
            "data:text/plain,secret",
            "javascript:alert(1)",
            "http://127.0.0.1/admin",
            "http://[::1]/admin",
            "http://169.254.169.254/latest/meta-data",
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeUrlError):
                validate_url(url, resolve=False)

    def test_rejects_wrong_source_host_and_credentials(self):
        with self.assertRaises(UnsafeUrlError):
            validate_url(
                "https://evil.example/product",
                allowed_hosts={"shop.example"},
                resolver=public_resolver,
            )
        with self.assertRaises(UnsafeUrlError):
            validate_url(
                "https://user:pass@shop.example/product",
                allowed_hosts={"shop.example"},
                resolver=public_resolver,
            )


class ConfirmationTests(unittest.TestCase):
    def test_confirmation_is_bound_and_single_use(self):
        token = issue_confirmation(
            "x" * 32,
            operation="delete_price_records",
            target="listing-1",
            expected_rows=4,
            now=100,
        )
        result = consume_confirmation(
            "x" * 32,
            token,
            operation="delete_price_records",
            target="listing-1",
            now=101,
        )
        self.assertEqual(result.expected_rows, 4)
        with self.assertRaises(ConfirmationError):
            consume_confirmation(
                "x" * 32,
                token,
                operation="delete_price_records",
                target="listing-1",
                now=101,
            )

    def test_confirmation_rejects_target_substitution(self):
        token = issue_confirmation(
            "x" * 32,
            operation="deactivate_listing",
            target="listing-1",
            expected_rows=1,
            now=100,
        )
        with self.assertRaises(ConfirmationError):
            consume_confirmation(
                "x" * 32,
                token,
                operation="deactivate_listing",
                target="listing-2",
                now=101,
            )


class VerifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_price_only_result_is_rejected(self):
        from backend.scrapers.verify import verify_listing_url

        class Scraper:
            BASE_URL = "https://shop.example"

            async def get_listing(self, _url):
                return ScrapeResult(url=_url, title="", price_eur=99.0, error=None)

        with (
            patch("backend.scrapers.verify.get_scraper", return_value=Scraper()),
            patch("backend.scrapers.verify.validate_url", side_effect=lambda value, **_: value),
        ):
            ok, *_rest = await verify_listing_url("shop", "https://shop.example/product")
        self.assertFalse(ok)

    async def test_final_page_identity_mismatch_is_rejected(self):
        from backend.scrapers.verify import verify_listing_url

        class Scraper:
            BASE_URL = "https://shop.example"

            async def get_listing(self, _url):
                return ScrapeResult(url=_url, title="Example GX20 Workstation", price_eur=99.0, error=None)

        with (
            patch("backend.scrapers.verify.get_scraper", return_value=Scraper()),
            patch("backend.scrapers.verify.validate_url", side_effect=lambda value, **_: value),
        ):
            ok, *_rest = await verify_listing_url(
                "shop", "https://shop.example/product", expected_product_name="Example GX10 Workstation"
            )
        self.assertFalse(ok)

class ProductIdentityTests(unittest.TestCase):
    def test_matches_same_product_and_rejects_neighbor_model(self):
        self.assertTrue(product_title_matches("Example GX10 Workstation", "Example GX10 Workstation - 128 GB"))
        self.assertFalse(product_title_matches("Example GX10 Workstation", "Example GX20 Workstation - 128 GB"))


class WebSocketCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_socket_is_removed(self):
        from backend.api.ws import manager, websocket_endpoint

        class FakeWebSocket:
            headers = {"origin": "http://localhost:3000"}
            client = None

            async def accept(self):
                return None

            async def receive_text(self):
                await asyncio.sleep(60)

            async def close(self, *_args, **_kwargs):
                return None

        websocket = FakeWebSocket()
        task = asyncio.create_task(websocket_endpoint(websocket))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn(websocket, manager.active)


if __name__ == "__main__":
    unittest.main()
