/**
 * Next.js 16 proxy (the new name for middleware in v16). Generates a
 * per-request CSP nonce and applies the nonce-based Content-Security-Policy to
 * every navigation request. Static assets, prefetches, and API routes skip the
 * proxy via the `matcher` config below.
 *
 * The other (static) security headers — HSTS, X-Frame-Options, nosniff,
 * Referrer-Policy, Permissions-Policy — live in next.config.ts `headers()` so
 * they also cover the static assets this matcher skips. Only the CSP needs the
 * per-request nonce, so only the CSP is set here.
 *
 * Trade-off: nonce-based CSP forces dynamic rendering (each request gets a
 * fresh nonce), so static optimization / ISR are off for routes that flow
 * through the proxy. Phase 3 accepts this — the dashboard polls live data
 * anyway, and the auth + Passkey flows we're about to land need dynamic
 * rendering regardless.
 */

import { NextRequest, NextResponse } from "next/server";

function buildCspHeader(nonce: string, isDev: boolean): string {
  // `'strict-dynamic'` lets the nonced script load further scripts without
  // their own nonce — required because Next.js bootstraps additional chunks
  // from the runtime. Dev needs `'unsafe-eval'` for React's dev-tools eval
  // path and `'unsafe-inline'` on style for Tailwind 4's dev styles; both
  // drop off in production.
  const scriptExtras = isDev ? " 'unsafe-eval'" : "";
  const styleSrc = isDev
    ? "'self' 'unsafe-inline'"
    : `'self' 'nonce-${nonce}'`;
  return [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${scriptExtras}`,
    `style-src ${styleSrc}`,
    `img-src 'self' blob: data:`,
    `font-src 'self' data:`,
    `connect-src 'self'`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `frame-ancestors 'none'`,
    `upgrade-insecure-requests`,
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";
  const csp = buildCspHeader(nonce, isDev);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    // Run on every page request except static assets, the optimized image
    // route, the favicon, generated image responses (icon/splash/og), the
    // well-known manifest path (JSON, not HTML), and prefetches from
    // `next/link` (prefetches don't need a fresh nonce and forcing dynamic
    // rendering on them costs perf for no security benefit).
    {
      source:
        "/((?!_next/static|_next/image|favicon.ico|opengraph-image|api/og/|\\.well-known/).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
