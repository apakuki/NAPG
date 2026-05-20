import { test, expect } from "@playwright/test";

test("home page renders the dashboard shell with the three monitor cards", async ({
  page,
}) => {
  // Stub the proxy route so the test does not depend on the agent running.
  await page.route("**/api/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        heartbeat: { error: "BASE_SEPOLIA_RPC_URL not set" },
        aerodrome: { error: "ZEROX_API_KEY not set" },
        morpho: { error: "BASE_RPC_URL not set (Morpho needs Base mainnet)" },
      }),
    });
  });

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: /NetAssure Protocol Guardian/i }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: /live monitor state/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /RPC heartbeat/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Aerodrome USDC\/USDT/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Morpho Blue/i })).toBeVisible();
});
