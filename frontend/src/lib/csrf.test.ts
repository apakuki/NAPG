import { describe, expect, it } from "vitest";

import { CsrfError, assertSameOrigin } from "./csrf";

function buildRequest(
  method: string,
  init: { host?: string; proto?: string; origin?: string; referer?: string } = {},
): Request {
  const headers = new Headers();
  if (init.host) headers.set("host", init.host);
  if (init.proto) headers.set("x-forwarded-proto", init.proto);
  if (init.origin) headers.set("origin", init.origin);
  if (init.referer) headers.set("referer", init.referer);
  return new Request("http://localhost:3000/api/auth/signout", {
    method,
    headers,
  });
}

describe("assertSameOrigin", () => {
  it("passes GET / HEAD / OPTIONS regardless of Origin", () => {
    for (const method of ["GET", "HEAD", "OPTIONS"]) {
      expect(() =>
        assertSameOrigin(buildRequest(method, { host: "napg.example" })),
      ).not.toThrow();
    }
  });

  it("accepts a POST whose Origin matches the request host", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", {
          host: "napg.example",
          proto: "https",
          origin: "https://napg.example",
        }),
      ),
    ).not.toThrow();
  });

  it("rejects a POST whose Origin is a different domain", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", {
          host: "napg.example",
          proto: "https",
          origin: "https://evil.example",
        }),
      ),
    ).toThrow(CsrfError);
  });

  it("falls back to Referer when Origin is missing", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", {
          host: "napg.example",
          proto: "https",
          referer: "https://napg.example/settings",
        }),
      ),
    ).not.toThrow();
  });

  it("rejects when Referer is a different origin", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", {
          host: "napg.example",
          proto: "https",
          referer: "https://evil.example/settings",
        }),
      ),
    ).toThrow(CsrfError);
  });

  it("rejects when both Origin and Referer are missing", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", { host: "napg.example", proto: "https" }),
      ),
    ).toThrow(CsrfError);
  });

  it("rejects when the Host header itself is missing", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", {
          origin: "https://napg.example",
        }),
      ),
    ).toThrow(/Host/);
  });

  it("uses X-Forwarded-Host + X-Forwarded-Proto when present", () => {
    const headers = new Headers({
      host: "localhost:3000",
      "x-forwarded-host": "napg.example",
      "x-forwarded-proto": "https",
      origin: "https://napg.example",
    });
    expect(() =>
      assertSameOrigin(
        new Request("https://napg.example/api/auth/signout", {
          method: "POST",
          headers,
        }),
      ),
    ).not.toThrow();
  });

  it("ignores malformed Referer values gracefully", () => {
    expect(() =>
      assertSameOrigin(
        buildRequest("POST", {
          host: "napg.example",
          proto: "https",
          referer: "not-a-url",
        }),
      ),
    ).toThrow(CsrfError);
  });
});
