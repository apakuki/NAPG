import { expect, test } from "@playwright/test";

// Bottom-nav presence + per-page navigation. The dashboard route's `/api/status`
// proxy is stubbed out so the test does not depend on the agent backend.
test("nav reaches every Phase 3 stub page", async ({ page }) => {
  await page.route("**/api/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        heartbeat: { error: "stub" },
        aerodrome: { error: "stub" },
        morpho: { error: "stub" },
        generated_at: 1_700_000_000,
      }),
    });
  });

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "NetAssure Protocol Guardian" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Breaches" }).click();
  await expect(page).toHaveURL(/\/breaches$/);
  await expect(
    page.getByRole("heading", { name: "Breach feed" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("protocol detail page reads the dynamic segment", async ({ page }) => {
  await page.goto("/protocols/aerodrome-usdc-usdt");
  await expect(
    page.getByRole("heading", {
      name: "Protocol detail: aerodrome-usdc-usdt",
    }),
  ).toBeVisible();
});
