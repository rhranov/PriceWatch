/**
 * Next.js Edge Middleware — injects the API key into every /api/* request
 * before it gets rewritten to the FastAPI backend.
 *
 * The key is read from PRICEWATCH_API_KEY in .env.local (never exposed to the browser).
 */

import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDevelopment = process.env.NODE_ENV === "development";
  const websocketUrl =
    process.env.NEXT_PUBLIC_PRICEWATCH_WS_URL ?? "ws://127.0.0.1:8000/ws";
  const contentSecurityPolicy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDevelopment ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self'",
    `connect-src 'self' ${websocketUrl} ws://localhost:8000 ws://127.0.0.1:8000`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", contentSecurityPolicy);

  if (request.nextUrl.pathname.startsWith("/api/")) {
    const apiKey = process.env.PRICEWATCH_API_KEY ?? "";
    if (apiKey.length < 32) {
      return NextResponse.json(
        { detail: "PriceWatch API proxy is not configured" },
        { status: 503 },
      );
    }

    const unsafeMethod = !["GET", "HEAD", "OPTIONS"].includes(request.method);
    if (unsafeMethod) {
      const origin = request.headers.get("origin");
      if (!origin || origin !== request.nextUrl.origin) {
        return NextResponse.json(
          { detail: "Cross-origin state changes are not allowed" },
          { status: 403 },
        );
      }
    }

    requestHeaders.set("X-API-Key", apiKey);
  }

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set("Content-Security-Policy", contentSecurityPolicy);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
