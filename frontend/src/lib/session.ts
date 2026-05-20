/**
 * Session token helpers for SIWF-authenticated routes.
 *
 * Token format (server-only — never exposed to JS via document.cookie):
 *
 *     base64url(JSON({ fid, exp })) "." hex(HMAC-SHA256(payload, secret))
 *
 * Stored in the `napg_session` cookie with `HttpOnly`, `Secure` (production
 * only — localhost dev is http), `SameSite=Lax`, no `Domain` (eTLD+1 only),
 * `Path=/`. Expires set client-side from `exp` so the cookie clears when the
 * payload would. Server still re-verifies on every authenticated request and
 * never trusts the client's `fid` claim (per Phase 3 security baseline).
 *
 * Reasoning for rolling our own instead of a JWT library: we already use the
 * same HMAC pattern in `napg.audit` and the surface here is two functions.
 * No JWT library = one fewer dep with its own audit surface.
 */

import { createHmac, timingSafeEqual } from "node:crypto";

import type { ResponseCookies } from "next/dist/server/web/spec-extension/cookies";
import type { ReadonlyRequestCookies } from "next/dist/server/web/spec-extension/adapters/request-cookies";

export const SESSION_COOKIE_NAME = "napg_session";
const DEFAULT_TTL_SECONDS = 24 * 60 * 60; // 24h

export interface SessionPayload {
  fid: number;
  address: `0x${string}`;
  exp: number; // unix seconds
}

function getSecret(): Buffer {
  const secret = process.env.NAPG_SESSION_SECRET;
  if (!secret) {
    throw new Error(
      "NAPG_SESSION_SECRET is not set; refusing to issue or verify session tokens.",
    );
  }
  return Buffer.from(secret, "utf-8");
}

function base64urlEncode(input: Buffer | string): string {
  const buf = typeof input === "string" ? Buffer.from(input, "utf-8") : input;
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function base64urlDecode(input: string): Buffer {
  const pad = input.length % 4 === 0 ? "" : "=".repeat(4 - (input.length % 4));
  return Buffer.from(input.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64");
}

function signPayload(payload: string, secret: Buffer): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

export function createSessionToken(
  fid: number,
  address: `0x${string}`,
  options: { ttlSeconds?: number; now?: () => number } = {},
): string {
  const now = options.now ? options.now() : Math.floor(Date.now() / 1000);
  const exp = now + (options.ttlSeconds ?? DEFAULT_TTL_SECONDS);
  const payload: SessionPayload = { fid, address, exp };
  const encoded = base64urlEncode(JSON.stringify(payload));
  const signature = signPayload(encoded, getSecret());
  return `${encoded}.${signature}`;
}

export function verifySessionToken(
  token: string,
  options: { now?: () => number } = {},
): SessionPayload | null {
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  const [encoded, signature] = parts;
  const secret = getSecret();
  const expected = signPayload(encoded, secret);

  // Constant-time comparison; both buffers must be the same length first.
  const expectedBuf = Buffer.from(expected, "hex");
  const providedBuf = Buffer.from(signature, "hex");
  if (expectedBuf.length !== providedBuf.length) return null;
  if (!timingSafeEqual(expectedBuf, providedBuf)) return null;

  let payload: SessionPayload;
  try {
    payload = JSON.parse(base64urlDecode(encoded).toString("utf-8")) as SessionPayload;
  } catch {
    return null;
  }
  if (
    typeof payload.fid !== "number" ||
    typeof payload.exp !== "number" ||
    typeof payload.address !== "string" ||
    !/^0x[0-9a-fA-F]{40}$/.test(payload.address)
  ) {
    return null;
  }
  const now = options.now ? options.now() : Math.floor(Date.now() / 1000);
  if (payload.exp <= now) return null;
  return payload;
}

export interface CookieOptions {
  isProduction: boolean;
  maxAgeSeconds: number;
}

export function sessionCookieOptions(opts: CookieOptions) {
  return {
    httpOnly: true,
    secure: opts.isProduction,
    sameSite: "lax" as const,
    path: "/",
    maxAge: opts.maxAgeSeconds,
  };
}

export function setSessionCookie(
  cookies: ResponseCookies,
  fid: number,
  address: `0x${string}`,
  options: { ttlSeconds?: number; isProduction?: boolean } = {},
): void {
  const ttl = options.ttlSeconds ?? DEFAULT_TTL_SECONDS;
  const isProduction =
    options.isProduction ?? process.env.NODE_ENV === "production";
  const token = createSessionToken(fid, address, { ttlSeconds: ttl });
  cookies.set(
    SESSION_COOKIE_NAME,
    token,
    sessionCookieOptions({ isProduction, maxAgeSeconds: ttl }),
  );
}

export function clearSessionCookie(cookies: ResponseCookies): void {
  cookies.set(SESSION_COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

export function getSessionFromCookies(
  cookies: ReadonlyRequestCookies,
): SessionPayload | null {
  const cookie = cookies.get(SESSION_COOKIE_NAME);
  if (!cookie?.value) return null;
  return verifySessionToken(cookie.value);
}
