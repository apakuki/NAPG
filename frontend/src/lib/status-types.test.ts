import { describe, expect, it } from "vitest";
import { isCardError } from "./status-types";

describe("isCardError", () => {
  it("returns true for {error: string}", () => {
    expect(isCardError({ error: "ZEROX_API_KEY not set" })).toBe(true);
  });

  it("returns false for probe data without an error field", () => {
    expect(isCardError({ chain_id: 84532, latency_ms: 100 })).toBe(false);
  });

  it("returns false when error is present but not a string", () => {
    expect(isCardError({ error: 42 } as unknown as object)).toBe(false);
  });
});
