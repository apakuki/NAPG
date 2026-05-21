/**
 * Origin/Referer-based CSRF guard.
 *
 * Why not a token? Tokens are needed when the server cannot trust the
 * request to identify its own origin -- classic <form> with no JS, or
 * APIs that legitimately need to be called cross-origin. Neither applies
 * here: every state-changing call comes from our own client code via
 * fetch(), so the browser always attaches a same-origin `Origin` header
 * for us. Re-checking that header server-side is simpler than minting,
 * storing, and rotating a double-submit token, and is the pattern
 * recommended by OWASP for cookie-authenticated SPAs.
 *
 * Spec: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#identifying-source-origin-via-originreferer-header
 *
 * Behaviour:
 *  - GET / HEAD / OPTIONS are passed through (safe methods).
 *  - For other methods, require `Origin` to exactly match the request's
 *    own scheme + host (derived from `x-forwarded-{proto,host}` first,
 *    then `host`). Fall back to `Referer` parsed for its origin if
 *    `Origin` is absent.
 *  - Missing both => reject. Crucially, no "open by default" path: an
 *    attacker controlling the user's browser can suppress neither
 *    header, but a fetch from an actual same-origin context always
 *    sends at least one.
 *
 * Throws `CsrfError` on failure so the caller can return a 403 response.
 */

export class CsrfError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CsrfError";
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function expectedOrigin(headers: Headers): string {
  const host = headers.get("x-forwarded-host") ?? headers.get("host");
  if (!host) {
    throw new CsrfError("no Host or X-Forwarded-Host header on the request");
  }
  const proto = headers.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}

function refererOrigin(referer: string | null): string | null {
  if (!referer) return null;
  try {
    return new URL(referer).origin;
  } catch {
    return null;
  }
}

export function assertSameOrigin(request: Request): void {
  if (SAFE_METHODS.has(request.method.toUpperCase())) return;

  const headers = request.headers;
  const expected = expectedOrigin(headers);
  const origin = headers.get("origin");
  if (origin) {
    if (origin === expected) return;
    throw new CsrfError(
      `Origin header ${origin} does not match expected ${expected}`,
    );
  }
  const refOrigin = refererOrigin(headers.get("referer"));
  if (refOrigin === expected) return;
  if (refOrigin === null) {
    throw new CsrfError(
      "no Origin or Referer header on a state-changing request",
    );
  }
  throw new CsrfError(
    `Referer origin ${refOrigin} does not match expected ${expected}`,
  );
}
