/**
 * Defensive redaction at the API boundary.
 *
 * The agent's Python side already redacts RPC URLs and never returns
 * secrets in its responses (see `napg.redact` and the per-card schema
 * validation in `napg.api`). This module is the matching frontend gate:
 * any JSON body that flows through a Next.js route handler should pass
 * through `redactResponse()` before serialization, so a future schema
 * change on the agent side can't silently leak a token-shaped field.
 *
 * Heuristics, not a guarantee:
 *  - Drop known sensitive *keys* recursively (case-insensitive). Things
 *    like `password`, `api_key`, `authorization`, `private_key`,
 *    `signature` are never user-relevant on the wire.
 *  - Mask values that look like bearer tokens or long base64 secrets
 *    (>40 chars, no whitespace, mostly URL-safe alphabet).
 *  - Mask the user-info segment of any URL value.
 *
 * Anything not matching is passed through unchanged. We do not redact
 * Ethereum addresses (the session route intentionally exposes the user's
 * own address to the same-origin client).
 */

const SENSITIVE_KEYS = new Set([
  "password",
  "passwd",
  "secret",
  "token",
  "api_key",
  "apikey",
  "authorization",
  "private_key",
  "privatekey",
  "signature",
  "mnemonic",
  "seed",
  "session_secret",
  "hmac_key",
]);

const TOKEN_SHAPE = /^[A-Za-z0-9_\-=+/]{40,}$/;

// Operational onchain identifiers: addresses (20 bytes = 40 hex chars) and
// tx hashes (32 bytes = 64 hex chars). These are public by definition --
// blockchains expose them -- and they happen to fit the opaque-token shape,
// so exempt them explicitly before the token rule runs.
const ETH_ADDRESS = /^0x[0-9a-fA-F]{40}$/;
const ETH_HASH = /^0x[0-9a-fA-F]{64}$/;

export function redactValue(value: unknown): unknown {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return redactString(value);
  if (typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(redactValue);
  return redactObject(value as Record<string, unknown>);
}

export function redactResponse<T>(body: T): T {
  return redactValue(body) as T;
}

function redactObject(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(obj)) {
    if (SENSITIVE_KEYS.has(key.toLowerCase())) {
      out[key] = "***";
      continue;
    }
    out[key] = redactValue(val);
  }
  return out;
}

function redactString(s: string): string {
  // URL with user-info segment: strip the credentials.
  if (/^https?:\/\/[^/@\s]+:[^/@\s]+@/.test(s)) {
    return s.replace(/^(https?:\/\/)[^/@\s]+:[^/@\s]+@/, "$1***@");
  }
  // Public onchain identifiers stay verbatim.
  if (ETH_ADDRESS.test(s) || ETH_HASH.test(s)) return s;
  // Long opaque tokens: keep first 4 / last 4 so logs are still grepable.
  if (s.length >= 40 && TOKEN_SHAPE.test(s)) {
    return `${s.slice(0, 4)}...${s.slice(-4)}`;
  }
  return s;
}
