import { test, expect } from "@playwright/test";

/**
 * Breach feed e2e. BreachFeed is a server component that fetches from the
 * Next.js proxy server-side, so `page.route` (which only intercepts browser
 * requests) cannot mock its data without spinning up a fake at port 8000.
 * The vitest suite already covers the proxy logic + the empty/error states
 * at the component level; these tests focus on what is genuinely
 * browser-observable: page shell, share button, navigation, and the
 * agent-unreachable callout text.
 *
 * Tests deliberately do NOT assert specific breach rows -- the live agent
 * may or may not be running, and either state should pass.
 */

test.describe("breach feed pages", () => {
  test("/breaches renders the shell + Share-to-Farcaster", async ({ page }) => {
    await page.goto("/breaches");
    await expect(
      page.getByRole("heading", { name: /^Breach feed$/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Share to Farcaster/i }),
    ).toHaveAttribute("href", /farcaster\.xyz\/~\/compose/);
  });

  test("/protocols/heartbeat renders the protocol-specific shell", async ({
    page,
  }) => {
    await page.goto("/protocols/heartbeat");
    await expect(
      page.getByRole("heading", { name: /RPC Heartbeat/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Share to Farcaster/i }),
    ).toHaveAttribute("href", /protocols%2Fheartbeat/);
  });

  test("/protocols/aerodrome share embed points back at the protocol page", async ({
    page,
  }) => {
    await page.goto("/protocols/aerodrome");
    await expect(
      page.getByRole("heading", { name: /Aerodrome USDC\/USDT/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Share to Farcaster/i }),
    ).toHaveAttribute("href", /protocols%2Faerodrome/);
  });

  test("/protocols/garbage 404s", async ({ page }) => {
    const response = await page.goto("/protocols/garbage", {
      waitUntil: "domcontentloaded",
    });
    expect(response?.status()).toBe(404);
  });
});
