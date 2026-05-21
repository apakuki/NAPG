/**
 * Single composable guard used by every state-changing or auth-adjacent
 * route. Centralised so the per-route handler stays short and we cannot
 * accidentally skip a layer when adding a new endpoint.
 *
 * Layers, in order:
 *   1. CSRF (Origin/Referer check on non-safe methods)
 *   2. Rate-limit (token bucket per key, see `lib/rate-limit.ts`)
 *
 * Returns either a `NextResponse` to short-circuit, or `null` to continue.
 * The caller composes the rest of its logic on the `null` branch.
 *
 * Limiters are module-scoped singletons so concurrent requests share state.
 * Single-instance only at Phase 3; Phase 5 mainnet cutover swaps the in-
 * memory backend for Redis (interface stays the same).
 */

import { NextResponse } from "next/server";

import { CsrfError, assertSameOrigin } from "./csrf";
import { RateLimiter, clientIpFromHeaders } from "./rate-limit";

// SIWF + signout endpoints are the public auth surface. Caps chosen for
// solo-dev Phase 3 traffic: a real user clicks Sign-in maybe twice an hour
// and the poll endpoint fires every 1.5 s for at most 5 min => ~200 polls.
// Set the capacity generously (60) and a steady fill (4/s) so a normal
// session never trips. An attacker probing channel tokens runs into 60
// requests before getting throttled.
const AUTH_LIMITER = new RateLimiter({ ratePerSec: 4, capacity: 60 });

export interface GuardOptions {
  /**
   * Stable name for the bucket key. Different routes get different
   * namespaces so signout traffic does not consume start tokens.
   */
  bucketName: string;
  /** Set true on POST/PUT/PATCH/DELETE routes. */
  csrf: boolean;
  /** Optional extra key suffix (e.g. fid) so an authed user has its own bucket. */
  identityKey?: string;
}

export function applyGuards(
  request: Request,
  options: GuardOptions,
): NextResponse | null {
  if (options.csrf) {
    try {
      assertSameOrigin(request);
    } catch (err) {
      if (err instanceof CsrfError) {
        return NextResponse.json(
          { error: "cross-origin request rejected" },
          { status: 403 },
        );
      }
      throw err;
    }
  }

  const ip = clientIpFromHeaders(request.headers);
  const key = options.identityKey
    ? `${options.bucketName}:${options.identityKey}:${ip}`
    : `${options.bucketName}:${ip}`;
  const decision = AUTH_LIMITER.take(key);
  if (!decision.allowed) {
    return NextResponse.json(
      { error: "rate limit exceeded" },
      {
        status: 429,
        headers: {
          "Retry-After": String(decision.retryAfterSeconds),
        },
      },
    );
  }
  return null;
}

/** Test-only: drop every bucket so the next call starts fresh. */
export function _resetGuardsForTests(): void {
  AUTH_LIMITER.reset();
}
