import type { NextConfig } from "next";

const backendUrl = process.env.PRICEWATCH_BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Don't strip/redirect trailing slashes. The API client calls trailing-slash
  // URLs (e.g. /api/products/) that FastAPI expects; without this, Next strips
  // the slash, FastAPI 307-redirects back, and the injected API key is lost on
  // the redirect -> 401.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  async headers() {
    const securityHeaders = [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ];
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
