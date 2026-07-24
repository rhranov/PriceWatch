"""
FastAPI application entry point.
Mounts all routers and the WebSocket endpoint.
"""

from contextlib import asynccontextmanager
import secrets

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.config import settings
from backend.api.routers import discoveries, prices, products, research, runs, scopes, sources
from backend.api.ws import router as ws_router

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# API Key middleware
# ---------------------------------------------------------------------------

# Routes that bypass the key check
_PUBLIC_PATHS = {"/api/health", "/ws", "/api/docs", "/api/redoc", "/openapi.json"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow public paths and OPTIONS (preflight)
        request_path = request.scope.get("path", "")
        if request.method == "OPTIONS" or request_path in _PUBLIC_PATHS:
            return await call_next(request)

        # Only protect /api/* routes
        if request_path.startswith("/api/"):
            provided = request.headers.get("X-API-Key", "")
            if not provided or not secrets.compare_digest(provided, settings.api_key):
                return Response(
                    content='{"detail":"Invalid or missing API key"}',
                    status_code=401,
                    media_type="application/json",
                )

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("PriceWatch API starting up", port=settings.app_port)
    # Warm up the DB connection pool so the first real request doesn't stall
    from sqlalchemy import text
    from backend.db.session import engine
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    log.info("PriceWatch API ready")
    yield
    log.info("PriceWatch API shutting down")


app = FastAPI(
    title="PriceWatch API",
    description="Price tracking and product discovery for configurable product scopes.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# API key middleware (must be added before CORS so it runs first)
app.add_middleware(ApiKeyMiddleware)

# CORS — allow Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reject attacker-controlled Host headers before routing can construct absolute
# redirects from them. PriceWatch is intentionally reachable only on loopback.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]"],
)

# Routers
app.include_router(scopes.router, prefix="/api/scopes", tags=["Scopes"])
app.include_router(sources.router, prefix="/api/sources", tags=["Sources"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(prices.router, prefix="/api/prices", tags=["Prices"])
app.include_router(discoveries.router, prefix="/api/discoveries", tags=["Discoveries"])
app.include_router(runs.router, prefix="/api/runs", tags=["Agent Runs"])
app.include_router(research.router, prefix="/api/research", tags=["Research Intelligence"])
app.include_router(ws_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
