import type { NextConfig } from "next";

// Baseline security headers applied to EVERY response, including the static
// assets under /_next/static that the proxy's matcher deliberately skips. The
// nonce-based Content-Security-Policy lives in src/proxy.ts (navigation routes
// only, since the nonce is per-request); these are static so they belong here
// where they also cover static assets. Addresses ZAP baseline 10021
// (nosniff on assets), 10035 (HSTS), and 10063 (Permissions-Policy on assets).
const securityHeaders = [
  // Honoured only over HTTPS; browsers ignore it on plain http (dev), so it is
  // safe to send unconditionally. Two years, includeSubDomains for the host.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
  },
];

const nextConfig: NextConfig = {
  // Emit a self-contained .next/standalone (minimal server.js + traced
  // node_modules) so the Docker image needs neither a full npm install nor
  // `next start`. See node_modules/next/dist/docs/.../config/.../output.md.
  output: "standalone",
  // Next sends `X-Powered-By: Next.js` by default; drop it so we do not leak
  // the framework name/version (ZAP baseline 10037).
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
