import { describe, expect, it } from "vitest";

import { RateLimiter, clientIpFromHeaders } from "./rate-limit";

function fixedNow() {
  let now = 1_700_000_000_000;
  return {
    advance(ms: number) {
      now += ms;
    },
    fn() {
      return now;
    },
  };
}

describe("RateLimiter", () => {
  it("allows up to `capacity` calls before throttling", () => {
    const clock = fixedNow();
    const lim = new RateLimiter({ ratePerSec: 1, capacity: 3, now: clock.fn });
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(true);
    const blocked = lim.take("k");
    expect(blocked.allowed).toBe(false);
    expect(blocked.retryAfterSeconds).toBe(1);
  });

  it("refills at ratePerSec", () => {
    const clock = fixedNow();
    const lim = new RateLimiter({ ratePerSec: 2, capacity: 2, now: clock.fn });
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(false);
    // 500ms refills exactly 1 token at 2/sec.
    clock.advance(500);
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(false);
  });

  it("caps refill at capacity (no over-fill while idle)", () => {
    const clock = fixedNow();
    const lim = new RateLimiter({ ratePerSec: 100, capacity: 2, now: clock.fn });
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(true);
    clock.advance(60_000); // 60s idle, would refill 6000 tokens uncapped.
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(true);
    expect(lim.take("k").allowed).toBe(false);
  });

  it("isolates buckets by key", () => {
    const lim = new RateLimiter({ ratePerSec: 0.001, capacity: 1 });
    expect(lim.take("alice").allowed).toBe(true);
    expect(lim.take("alice").allowed).toBe(false);
    expect(lim.take("bob").allowed).toBe(true);
  });

  it("rejects invalid configs", () => {
    expect(() => new RateLimiter({ ratePerSec: 0, capacity: 1 })).toThrow();
    expect(() => new RateLimiter({ ratePerSec: 1, capacity: 0 })).toThrow();
  });
});

describe("clientIpFromHeaders", () => {
  it("uses the left-most X-Forwarded-For entry", () => {
    const h = new Headers({ "x-forwarded-for": "203.0.113.5, 10.0.0.1" });
    expect(clientIpFromHeaders(h)).toBe("203.0.113.5");
  });

  it("falls back to X-Real-IP when XFF is absent", () => {
    const h = new Headers({ "x-real-ip": "203.0.113.5" });
    expect(clientIpFromHeaders(h)).toBe("203.0.113.5");
  });

  it("returns 'local' when no proxy header is present", () => {
    expect(clientIpFromHeaders(new Headers())).toBe("local");
  });
});
