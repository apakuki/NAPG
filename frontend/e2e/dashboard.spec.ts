import { test, expect, Route } from "@playwright/test";

// Realistic-shaped probe response. The dashboard reads the fields directly,
// so the test mirrors the actual schema rather than using a half-stub.
function healthyBody(blockNumber: number) {
  return {
    heartbeat: {
      rpc_url: "https://sepolia.example/<redacted>",
      chain_id: 84532,
      latency_ms: 123,
      block: {
        number: blockNumber,
        hash: "0x" + "aa".repeat(32),
        parent_hash: "0x" + "bb".repeat(32),
        timestamp: 1_700_000_000,
      },
      reorg_detected: false,
      observed_at: 1_700_000_001,
    },
    aerodrome: {
      chain_id: 8453,
      sell_token: "0xUSDC",
      buy_token: "0xUSDT",
      sell_amount: 10_000_000_000,
      buy_amount: 9_995_000_000,
      liquidity_available: true,
      quoted_rate: 0.9995,
      peg_deviation_bps: 5,
      sources: ["Aerodrome_V3", "Uniswap_V4"],
      block_number: blockNumber,
      latency_ms: 200,
      observed_at: 1_700_000_002,
    },
    morpho: {
      chain_id: 8453,
      block_number: blockNumber,
      block_timestamp: 1_700_000_000,
      markets: [
        {
          label: "WETH-USDC",
          market_id: "0x" + "11".repeat(32),
          loan_symbol: "USDC",
          collateral_symbol: "WETH",
          total_supply_assets: 77_000_000_000_000,
          total_borrow_assets: 69_000_000_000_000,
          utilization_bps: 9039,
          last_update: 1_700_000_000,
          staleness_seconds: 30,
          block_number: blockNumber,
          observed_at: 1_700_000_002,
        },
      ],
      latency_ms: 80,
      observed_at: 1_700_000_002,
    },
  };
}

test("auto-poll: the dashboard hits /api/status more than once over 11 s", async ({
  page,
}) => {
  let hits = 0;
  await page.route("**/api/status", async (route: Route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(healthyBody(46_225_300 + hits)),
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Aerodrome USDC\/USDT/i })).toBeVisible();
  await expect.poll(() => hits, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);

  // Wait the full 10s poll interval plus a small buffer for the second fetch.
  await page.waitForTimeout(11_000);
  expect(hits).toBeGreaterThanOrEqual(2);
});

test("per-card degrade: only the aerodrome card shows its error", async ({ page }) => {
  await page.route("**/api/status", async (route: Route) => {
    const body = healthyBody(46_225_400);
    // Replace aerodrome with the CardError envelope the API returns when
    // ZEROX_API_KEY is unset, leaving the other two cards healthy.
    const broken = {
      ...body,
      aerodrome: { error: "ZEROX_API_KEY not set" },
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(broken),
    });
  });

  await page.goto("/");
  await expect(page.getByText("ZEROX_API_KEY not set")).toBeVisible();
  // The other cards still render their fields, not an error.
  await expect(page.getByText(/WETH-USDC/i)).toBeVisible();
  await expect(page.getByText(/Aerodrome_V3/)).toHaveCount(0);
});

test("transport error: the dashboard shows the cannot-reach banner on 502", async ({
  page,
}) => {
  await page.route("**/api/status", async (route: Route) => {
    await route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({ error: "cannot reach agent at http://127.0.0.1:8000" }),
    });
  });

  await page.goto("/");
  await expect(
    page.getByRole("alert").filter({ hasText: /cannot reach the agent api/i }),
  ).toBeVisible();
});

test("tab-visibility: hiding the tab stops polling; showing it again resumes", async ({
  page,
}) => {
  let hits = 0;
  await page.route("**/api/status", async (route: Route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(healthyBody(46_225_500 + hits)),
    });
  });

  await page.goto("/");
  await expect.poll(() => hits, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
  const hitsWhenLoaded = hits;

  // Simulate hiding the tab. The dashboard's visibilitychange handler is
  // wired to clear the interval when document.hidden is true.
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });

  // No new requests should fire while hidden, even past one poll interval.
  await page.waitForTimeout(11_000);
  expect(hits).toBe(hitsWhenLoaded);

  // Restore visibility — handler fires an immediate refresh and restarts polling.
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect.poll(() => hits, { timeout: 5_000 }).toBeGreaterThan(hitsWhenLoaded);
});

test("console: page loads without browser console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));

  await page.route("**/api/status", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(healthyBody(46_225_600)),
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Live monitor state/i })).toBeVisible();
  // Let the first fetch complete and a re-render settle.
  await page.waitForTimeout(500);

  expect(errors).toEqual([]);
});
