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

  // Each dashboard card now has its own "View breaches →" link, so the
  // nav-link match has to be exact to avoid strict-mode ambiguity.
  await page.getByRole("link", { name: "Breaches", exact: true }).click();
  await expect(page).toHaveURL(/\/breaches$/);
  await expect(
    page.getByRole("heading", { name: "Breach feed" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("protocol detail page reads the dynamic segment", async ({ page }) => {
  // The id whitelist is {heartbeat, aerodrome, morpho}; everything else 404s.
  await page.goto("/protocols/aerodrome");
  await expect(
    page.getByRole("heading", { name: "Aerodrome USDC/USDT" }),
  ).toBeVisible();
});
