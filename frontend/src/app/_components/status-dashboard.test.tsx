import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusDashboard } from "./status-dashboard";
import type { StatusResponse } from "@/lib/status-types";

function healthyResponse(): StatusResponse {
  return {
    heartbeat: {
      rpc_url: "https://sepolia.example/<redacted>",
      chain_id: 84532,
      latency_ms: 123,
      block: {
        number: 42_000_000,
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
      buy_amount: 10_001_000_000,
      liquidity_available: true,
      quoted_rate: 1.0001,
      peg_deviation_bps: 1,
      sources: ["Aerodrome_V3"],
      block_number: 1234,
      latency_ms: 200,
      observed_at: 1_700_000_002,
    },
    morpho: {
      chain_id: 8453,
      block_number: 5678,
      block_timestamp: 1_700_000_000,
      markets: [
        {
          label: "WETH-USDC",
          market_id: "0x" + "11".repeat(32),
          loan_symbol: "USDC",
          collateral_symbol: "WETH",
          total_supply_assets: 10 ** 13,
          total_borrow_assets: 8 * 10 ** 12,
          utilization_bps: 8000,
          last_update: 1_700_000_000,
          staleness_seconds: 10,
          block_number: 5678,
          observed_at: 1_700_000_002,
        },
      ],
      latency_ms: 80,
      observed_at: 1_700_000_002,
    },
  };
}

describe("StatusDashboard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders three card titles", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(healthyResponse()), { status: 200 }),
      ),
    );
    render(<StatusDashboard />);

    await waitFor(() => {
      expect(screen.getByText("RPC heartbeat")).toBeInTheDocument();
      expect(screen.getByText("Aerodrome USDC/USDT")).toBeInTheDocument();
      expect(screen.getByText("Morpho Blue")).toBeInTheDocument();
    });
  });

  it("renders live data fields after first fetch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(healthyResponse()), { status: 200 }),
      ),
    );
    render(<StatusDashboard />);

    await waitFor(() => {
      expect(screen.getByText("42,000,000")).toBeInTheDocument(); // block.number
      expect(screen.getByText("Aerodrome_V3")).toBeInTheDocument();
      expect(screen.getByText("WETH-USDC")).toBeInTheDocument();
      expect(screen.getByText("80.00%")).toBeInTheDocument(); // utilisation 8000bps
    });
  });

  it("shows per-card error when the agent reports one", async () => {
    const body = healthyResponse();
    body.aerodrome = { error: "ZEROX_API_KEY not set" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })),
    );
    render(<StatusDashboard />);

    await waitFor(() => {
      expect(screen.getByText("ZEROX_API_KEY not set")).toBeInTheDocument();
      // Healthy cards still render
      expect(screen.getByText("42,000,000")).toBeInTheDocument();
    });
  });

  it("shows a transport error banner when /api/status returns 502", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ error: "cannot reach agent at http://127.0.0.1:8000" }),
          { status: 502 },
        ),
      ),
    );
    render(<StatusDashboard />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/cannot reach agent/i);
    });
  });

  it("polls again on the 10s interval", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(JSON.stringify(healthyResponse()), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<StatusDashboard />);

      await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

      await vi.advanceTimersByTimeAsync(10_000);
      await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    } finally {
      vi.useRealTimers();
    }
  });
});
