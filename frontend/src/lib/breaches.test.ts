import { describe, expect, it } from "vitest";

import {
  formatTimestamp,
  isBreachFeedError,
  type BreachFeedError,
  type BreachFeedResponse,
} from "./breaches";

describe("formatTimestamp", () => {
  it("formats an ISO timestamp as UTC with full precision", () => {
    expect(formatTimestamp("2026-05-21T03:04:05Z")).toBe(
      "2026-05-21 03:04:05 UTC",
    );
  });

  it("zero-pads single-digit fields", () => {
    expect(formatTimestamp("2026-01-02T03:04:05Z")).toBe(
      "2026-01-02 03:04:05 UTC",
    );
  });

  it("returns the input unchanged if it is not parseable", () => {
    expect(formatTimestamp("not-a-date")).toBe("not-a-date");
  });
});

describe("isBreachFeedError", () => {
  it("narrows error responses", () => {
    const ok: BreachFeedResponse = { items: [], total_returned: 0 };
    const err: BreachFeedError = { error: "agent unreachable" };
    expect(isBreachFeedError(ok)).toBe(false);
    expect(isBreachFeedError(err)).toBe(true);
  });
});
