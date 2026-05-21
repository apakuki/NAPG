import { describe, expect, it } from "vitest";

import { summarizeCapabilities } from "./capabilities";

describe("summarizeCapabilities", () => {
  it("returns both flags true when atomic supported + paymasterService.supported", () => {
    expect(
      summarizeCapabilities({
        atomic: { status: "supported" },
        paymasterService: { supported: true },
      }),
    ).toEqual({ batch: true, paymaster: true });
  });

  it("treats atomic.status='ready' as batch supported (per EIP-5792)", () => {
    expect(
      summarizeCapabilities({ atomic: { status: "ready" } }),
    ).toEqual({ batch: true, paymaster: false });
  });

  it("treats atomic.status='unsupported' as batch=false", () => {
    expect(
      summarizeCapabilities({
        atomic: { status: "unsupported" },
        paymasterService: { supported: true },
      }),
    ).toEqual({ batch: false, paymaster: true });
  });

  it("returns false for both when caps is missing the keys", () => {
    expect(summarizeCapabilities({})).toEqual({ batch: false, paymaster: false });
  });

  it("returns false for both when caps is null or undefined", () => {
    expect(summarizeCapabilities(null)).toEqual({ batch: false, paymaster: false });
    expect(summarizeCapabilities(undefined)).toEqual({
      batch: false,
      paymaster: false,
    });
  });

  it("treats paymasterService.supported=false as false", () => {
    expect(
      summarizeCapabilities({
        atomic: { status: "supported" },
        paymasterService: { supported: false },
      }),
    ).toEqual({ batch: true, paymaster: false });
  });

  it("ignores extra capability keys it does not understand", () => {
    const result = summarizeCapabilities({
      atomic: { status: "supported" },
      paymasterService: { supported: true },
      futureFeature: { magic: 42 },
    });
    expect(result).toEqual({ batch: true, paymaster: true });
  });
});
