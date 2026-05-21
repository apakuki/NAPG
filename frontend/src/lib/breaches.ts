/**
 * Shared types + parsing for the breach feed. The shape mirrors the agent's
 * `napg.policy.breaches.Breach` model so changes only need to be made in two
 * places (the Pydantic model and this file) until we generate the client
 * from an OpenAPI schema in Phase 5.
 */

export type BreachSource = "heartbeat" | "aerodrome" | "morpho";

export const BREACH_SOURCES: readonly BreachSource[] = [
  "heartbeat",
  "aerodrome",
  "morpho",
] as const;

export interface BreachPayload {
  rule: string;
  source: string;
  severity: "warn" | "critical" | string;
  threshold: number | string | boolean;
  actual: number | string | boolean;
  message: string;
  detected_at: number;
}

export interface BreachFeedItem {
  id: number;
  recorded_at: string;
  payload: BreachPayload;
}

export interface BreachFeedResponse {
  items: BreachFeedItem[];
  total_returned: number;
}

export interface BreachFeedError {
  error: string;
}

export function isBreachFeedError(
  body: BreachFeedResponse | BreachFeedError,
): body is BreachFeedError {
  return "error" in body;
}

/**
 * Format an ISO timestamp as `YYYY-MM-DD HH:MM:SS UTC` -- audit-log timestamps
 * are operational data, not marketing, so keep them precise and unambiguous
 * (no relative "5 minutes ago" cuteness).
 */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ` +
    `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`
  );
}
