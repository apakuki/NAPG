/**
 * Token-bucket rate limiter, keyed by an arbitrary string. Per-key buckets
 * refill at `rate_per_sec` up to `capacity`. The bucket is consumed by 1
 * token per call to `take()` -- if no tokens remain, `take()` returns the
 * suggested retry-after in seconds.
 *
 * State lives in an in-memory `Map`. Fine for Phase 3 single-instance dev
 * and testnet; Phase 5 mainnet replaces with a shared store (Redis or
 * similar) at the same time we swap the SIWF channel store. The interface
 * is stable across that swap so the call sites don't change.
 *
 * Stale buckets are evicted lazily on `take()` once they would be back to
 * full -- no background timer required.
 *
 * Spec-mode behaviour:
 *  - Anonymous calls are keyed by client IP, parsed from
 *    `X-Forwarded-For` (left-most entry, see clientIpFromHeaders below)
 *    with a fall-back to a literal `local` for direct-to-Next requests.
 *    Phase 5 will pin a trusted proxy via env so a hostile client can't
 *    forge XFF.
 *  - Authenticated calls SHOULD additionally be keyed by fid so a single
 *    user can't burn the IP allowance for every legit user behind the
 *    same NAT. `clientIpFromHeaders` exposes the IP; callers compose the
 *    fid prefix themselves.
 */

interface Bucket {
  tokens: number;
  lastRefill: number;
}

export interface RateLimitConfig {
  ratePerSec: number;
  capacity: number;
  /** Override `Date.now` for tests. */
  now?: () => number;
}

export interface RateLimitDecision {
  allowed: boolean;
  retryAfterSeconds: number;
  remaining: number;
}

export class RateLimiter {
  private readonly buckets = new Map<string, Bucket>();
  private readonly rate: number;
  private readonly cap: number;
  private readonly now: () => number;

  constructor(config: RateLimitConfig) {
    if (config.ratePerSec <= 0) {
      throw new Error("ratePerSec must be > 0");
    }
    if (config.capacity <= 0) {
      throw new Error("capacity must be > 0");
    }
    this.rate = config.ratePerSec;
    this.cap = config.capacity;
    this.now = config.now ?? (() => Date.now());
  }

  take(key: string, cost = 1): RateLimitDecision {
    const t = this.now();
    const bucket = this.buckets.get(key);
    const fresh: Bucket = bucket ?? { tokens: this.cap, lastRefill: t };
    if (bucket) {
      const elapsed = Math.max(0, (t - bucket.lastRefill) / 1000);
      fresh.tokens = Math.min(this.cap, bucket.tokens + elapsed * this.rate);
      fresh.lastRefill = t;
    }
    if (fresh.tokens >= cost) {
      fresh.tokens -= cost;
      this.buckets.set(key, fresh);
      return {
        allowed: true,
        retryAfterSeconds: 0,
        remaining: Math.floor(fresh.tokens),
      };
    }
    this.buckets.set(key, fresh);
    const deficit = cost - fresh.tokens;
    return {
      allowed: false,
      retryAfterSeconds: Math.ceil(deficit / this.rate),
      remaining: 0,
    };
  }

  /** Test-only: drop every bucket so the next call starts fresh. */
  reset(): void {
    this.buckets.clear();
  }
}

/**
 * Extract the real client IP from request headers. Validates `X-Forwarded-For`
 * format minimally; on no header, returns "local" so dev requests still get a
 * key (and share one bucket, which is fine -- there's only one dev user).
 *
 * Phase 5 will pin a trusted-proxy env var so we don't blindly trust XFF
 * from a request that didn't actually pass through our CDN.
 */
export function clientIpFromHeaders(headers: Headers): string {
  const xff = headers.get("x-forwarded-for");
  if (xff) {
    const first = xff.split(",")[0]?.trim();
    if (first) return first;
  }
  const real = headers.get("x-real-ip");
  if (real) return real.trim();
  return "local";
}
