from __future__ import annotations

import pathlib
import sys
import unittest

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_server.server import (
    PriceWatchApi,
    PriceWatchApiError,
    mcp,
    validate_api_url,
)


class ApiUrlTests(unittest.TestCase):
    def test_accepts_loopback_origins(self):
        self.assertEqual(
            validate_api_url("http://127.0.0.1:8000/"),
            "http://127.0.0.1:8000",
        )
        self.assertEqual(
            validate_api_url("http://localhost:9000"),
            "http://localhost:9000",
        )

    def test_rejects_non_loopback_and_credentialed_urls(self):
        for value in (
            "https://127.0.0.1:8000",
            "http://pricewatch.example:8000",
            "http://user:pass@127.0.0.1:8000",
            "http://127.0.0.1:8000/api",
            "http://127.0.0.1:8000?debug=true",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_api_url(value)


class ApiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_api_key_and_returns_json(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["X-API-Key"], "test-secret")
            self.assertEqual(request.url.path, "/api/products")
            return httpx.Response(200, json=[{"name": "Example"}])

        api = PriceWatchApi(
            "http://127.0.0.1:8000",
            "test-secret",
            transport=httpx.MockTransport(handler),
        )

        result = await api.request("GET", "/api/products")

        self.assertEqual(result, [{"name": "Example"}])

    async def test_rejects_paths_outside_api(self):
        api = PriceWatchApi("http://127.0.0.1:8000", "test-secret")

        with self.assertRaises(ValueError):
            await api.request("GET", "/admin")

    async def test_does_not_follow_redirects(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(307, headers={"Location": "http://attacker.invalid/"})

        api = PriceWatchApi(
            "http://127.0.0.1:8000",
            "test-secret",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaisesRegex(PriceWatchApiError, "unexpected redirect"):
            await api.request("GET", "/api/products")

    async def test_api_error_never_contains_the_key(self):
        secret = "secret-value-that-must-not-leak"

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Invalid or missing API key"})

        api = PriceWatchApi(
            "http://127.0.0.1:8000",
            secret,
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(PriceWatchApiError) as caught:
            await api.request("GET", "/api/products")
        self.assertNotIn(secret, str(caught.exception))


class ToolSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_only_the_intended_tools(self):
        tools = await mcp.list_tools()

        self.assertEqual(
            {tool.name for tool in tools},
            {
                "finish_research_run",
                "list_discoveries",
                "list_products",
                "list_runs",
                "list_scopes",
                "list_sources",
                "pricewatch_health",
                "record_research_signal",
                "source_health",
                "start_research_run",
                "submit_discovery",
            },
        )
        self.assertNotIn("approve_discovery", {tool.name for tool in tools})
        self.assertFalse(any("delete" in tool.name for tool in tools))

    async def test_stdio_server_initializes_and_lists_tools(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=repo_root,
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()

        self.assertIn(
            "submit_discovery",
            {tool.name for tool in result.tools},
        )


if __name__ == "__main__":
    unittest.main()
