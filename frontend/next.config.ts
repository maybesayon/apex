import type { NextConfig } from "next";

/**
 * Proxy /api/* to the FastAPI backend.
 *
 * This keeps the browser on ONE origin. Session cookies are httpOnly and
 * SameSite=Lax, and Lax cookies are not sent cross-origin — so without this
 * rewrite the frontend would have to fall back to SameSite=None, which is
 * weaker and requires HTTPS everywhere. Proxying is both simpler and stricter.
 */
const API_ORIGIN = process.env.APEX_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
