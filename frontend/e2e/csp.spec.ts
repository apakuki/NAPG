import { expect, test } from "@playwright/test";

// Proxy generates a per-request CSP nonce. The browser-side assertion is that
// the response carries a CSP header with the expected directives and that the
// nonce is unique across requests.
test("CSP header is present with strict directives and a per-request nonce", async ({
  page,
}) => {
  const first = await page.goto("/");
  const firstCsp = first?.headers()["content-security-policy"];
  expect(firstCsp, "first request CSP").toBeTruthy();
  expect(firstCsp).toContain("default-src 'self'");
  expect(firstCsp).toContain("frame-ancestors 'none'");
  expect(firstCsp).toContain("object-src 'none'");
  expect(firstCsp).toContain("upgrade-insecure-requests");
  const firstNonceMatch = firstCsp!.match(/'nonce-([^']+)'/);
  expect(firstNonceMatch, "first request nonce").not.toBeNull();

  const second = await page.goto("/breaches");
  const secondCsp = second?.headers()["content-security-policy"];
  expect(secondCsp).toBeTruthy();
  const secondNonceMatch = secondCsp!.match(/'nonce-([^']+)'/);
  expect(secondNonceMatch).not.toBeNull();
  expect(secondNonceMatch![1]).not.toBe(firstNonceMatch![1]);
});

test("security headers (X-Frame-Options, Referrer-Policy, etc.) are set", async ({
  page,
}) => {
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["permissions-policy"]).toContain("camera=()");
});
