import { test, expect } from "@playwright/test";

test("home page shows the NAPG title", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /NetAssure Protocol Guardian/i })
  ).toBeVisible();
});
