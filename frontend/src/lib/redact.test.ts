import { describe, expect, it } from "vitest";

import { redactResponse, redactValue } from "./redact";

describe("redactValue", () => {
  it("masks sensitive keys regardless of case", () => {
    expect(
      redactValue({
        password: "hunter2",
        API_KEY: "fake-test-fixture-value",
        nested: { signature: "0xabc" },
      }),
    ).toEqual({
      password: "***",
      API_KEY: "***",
      nested: { signature: "***" },
    });
  });

  it("strips userinfo from URL strings", () => {
    expect(
      redactValue("https://user:secret@example.com/path"),
    ).toBe("https://***@example.com/path");
  });

  it("partially masks long opaque tokens", () => {
    const token = "abcd" + "x".repeat(50) + "wxyz";
    expect(redactValue(token)).toBe("abcd...wxyz");
  });

  it("leaves short / human-readable strings alone", () => {
    expect(redactValue("hello world")).toBe("hello world");
    expect(redactValue("samuel.base.eth")).toBe("samuel.base.eth");
  });

  it("preserves ethereum addresses (intentionally exposed to same-origin)", () => {
    const addr = "0x1234567890abcdef1234567890abcdef12345678";
    expect(redactValue(addr)).toBe(addr);
  });

  it("preserves ethereum tx hashes (32 bytes / 64 hex chars)", () => {
    const hash =
      "0xc69602fd192ea93f5df4fb485fffe48fab57340693cc725944b7133aac89c77c";
    expect(redactValue(hash)).toBe(hash);
  });

  it("walks arrays", () => {
    expect(
      redactValue([{ password: "x" }, "plain", "https://u:p@example.com/"]),
    ).toEqual([{ password: "***" }, "plain", "https://***@example.com/"]);
  });

  it("returns null / undefined / primitives unchanged", () => {
    expect(redactValue(null)).toBe(null);
    expect(redactValue(undefined)).toBe(undefined);
    expect(redactValue(42)).toBe(42);
    expect(redactValue(true)).toBe(true);
  });
});

describe("redactResponse", () => {
  it("preserves a clean response unchanged", () => {
    const body = {
      authenticated: true,
      fid: 9152,
      address: "0xabc",
      exp: 1_700_000_000,
    };
    expect(redactResponse(body)).toEqual(body);
  });
});
