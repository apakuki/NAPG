import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  createSessionToken,
  SESSION_COOKIE_NAME,
  sessionCookieOptions,
  verifySessionToken,
} from "./session";

const SECRET = "test-secret-do-not-use-in-prod";
let originalSecret: string | undefined;

beforeEach(() => {
  originalSecret = process.env.NAPG_SESSION_SECRET;
  process.env.NAPG_SESSION_SECRET = SECRET;
});

afterEach(() => {
  if (originalSecret === undefined) {
    delete process.env.NAPG_SESSION_SECRET;
  } else {
    process.env.NAPG_SESSION_SECRET = originalSecret;
  }
});

describe("session token", () => {
  it("round-trips fid", () => {
    const token = createSessionToken(12345, { ttlSeconds: 60 });
    const payload = verifySessionToken(token);
    expect(payload?.fid).toBe(12345);
  });

  it("rejects a token signed with a different secret", () => {
    const token = createSessionToken(1, { ttlSeconds: 60 });
    process.env.NAPG_SESSION_SECRET = "another-secret";
    expect(verifySessionToken(token)).toBeNull();
  });

  it("rejects a tampered payload", () => {
    const token = createSessionToken(1, { ttlSeconds: 60 });
    const [, signature] = token.split(".");
    // Flip the fid by re-encoding a new payload with the same signature.
    const fakePayload = Buffer.from(JSON.stringify({ fid: 999, exp: 99999999999 }))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/g, "");
    const tampered = `${fakePayload}.${signature}`;
    expect(verifySessionToken(tampered)).toBeNull();
  });

  it("rejects an expired token", () => {
    const token = createSessionToken(1, { ttlSeconds: -10 });
    expect(verifySessionToken(token)).toBeNull();
  });

  it("rejects malformed tokens", () => {
    expect(verifySessionToken("not-a-token")).toBeNull();
    expect(verifySessionToken("only.one.dot.too.many")).toBeNull();
    expect(verifySessionToken("")).toBeNull();
  });

  it("throws clearly when NAPG_SESSION_SECRET is missing", () => {
    delete process.env.NAPG_SESSION_SECRET;
    expect(() => createSessionToken(1)).toThrow(/NAPG_SESSION_SECRET/);
  });

  it("verifies a fresh token issued seconds ago", () => {
    const token = createSessionToken(42, {
      ttlSeconds: 30,
      now: () => 1_000_000_000,
    });
    const payload = verifySessionToken(token, { now: () => 1_000_000_010 });
    expect(payload?.fid).toBe(42);
    expect(payload?.exp).toBe(1_000_000_030);
  });
});

describe("session cookie options", () => {
  it("sets HttpOnly + SameSite=Lax always", () => {
    const opts = sessionCookieOptions({ isProduction: false, maxAgeSeconds: 60 });
    expect(opts.httpOnly).toBe(true);
    expect(opts.sameSite).toBe("lax");
    expect(opts.path).toBe("/");
  });

  it("flips Secure on in production", () => {
    expect(
      sessionCookieOptions({ isProduction: true, maxAgeSeconds: 60 }).secure,
    ).toBe(true);
    expect(
      sessionCookieOptions({ isProduction: false, maxAgeSeconds: 60 }).secure,
    ).toBe(false);
  });
});

describe("constants", () => {
  it("cookie name is stable across imports", () => {
    expect(SESSION_COOKIE_NAME).toBe("napg_session");
  });
});
