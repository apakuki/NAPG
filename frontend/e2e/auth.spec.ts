import { createHmac } from "node:crypto";
import { test, expect } from "@playwright/test";

// Must match playwright.config.ts webServer.env.NAPG_SESSION_SECRET.
const TEST_SESSION_SECRET = "playwright-test-secret-do-not-use-elsewhere";

function mintSessionCookie(fid: number, address: `0x${string}`): string {
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const payloadJson = JSON.stringify({ fid, address, exp });
  const encoded = Buffer.from(payloadJson, "utf-8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  const sig = createHmac("sha256", Buffer.from(TEST_SESSION_SECRET, "utf-8"))
    .update(encoded)
    .digest("hex");
  return `${encoded}.${sig}`;
}

test.describe("SIWF auth surface", () => {
  test("unauthed /settings shows the Sign-in card with Connect Smart Wallet", async ({
    page,
  }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /^Identity$/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Sign in with Farcaster/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Connect Smart Wallet/i }),
    ).toBeVisible();
  });

  test("clicking Sign-in opens a channel and shows the Farcaster deep link", async ({
    page,
  }) => {
    await page.route("**/api/auth/siwf/start", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          channelToken: "playwright-channel-token",
          url: "https://farcaster.xyz/~/siwf?channelToken=playwright-channel-token",
        }),
      });
    });
    // Keep the poll endpoint returning pending so the test does not race a
    // mocked "completed" reload before we assert.
    await page.route("**/api/auth/siwf/poll**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ state: "pending" }),
      });
    });

    await page.goto("/settings");
    await page.getByRole("button", { name: /Sign in with Farcaster/i }).click();

    await expect(
      page.getByRole("link", { name: /Open in Farcaster/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Open in Farcaster/i }),
    ).toHaveAttribute(
      "href",
      "https://farcaster.xyz/~/siwf?channelToken=playwright-channel-token",
    );
    await expect(
      page.getByRole("button", { name: /^Cancel$/ }),
    ).toBeVisible();
  });

  test("signed-in /settings shows fid + sign-out, server-renders the Basename or fallback", async ({
    context,
    page,
  }) => {
    // Forge a valid HMAC-signed cookie matching the webServer's secret. The
    // address belongs to jesse.base.eth on Base mainnet; the basename
    // resolver may either return the name or null depending on whether
    // BASE_RPC_URL is reachable from the test env. The card MUST render
    // either way, so the assertion is on the fid line + the sign-out
    // button, not the basename specifically.
    await context.addCookies([
      {
        name: "napg_session",
        value: mintSessionCookie(
          1,
          "0x2211d1D0020DAEA8039E46Cf1367962070d77DA9",
        ),
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax",
      },
    ]);
    await page.goto("/settings");
    await expect(page.getByText(/Signed in as/)).toBeVisible();
    await expect(page.getByText(/fid 1\b/)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^Sign out$/ }),
    ).toBeVisible();
  });
});
