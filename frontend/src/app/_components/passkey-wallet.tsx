"use client";

import { useMemo } from "react";
import {
  useCapabilities,
  useConnect,
  useConnection,
  useConnectors,
  useDisconnect,
} from "wagmi";

import {
  summarizeCapabilities,
  type RawCapabilities,
} from "@/lib/capabilities";
import { truncateAddress } from "@/lib/basenames";

/**
 * Smart Wallet connect / capability panel. Distinct from the SIWF identity
 * above it: SIWF proves the user owns a Farcaster custody / auth address;
 * this section proves the user controls a Passkey-backed Coinbase Smart
 * Wallet, which is the wallet that will actually hold positions and pay for
 * Guardian Mode in later phases.
 *
 * Phase 3 deliberately stops short of submitting transactions. We connect,
 * we show the address, and we read EIP-5792 `wallet_getCapabilities` to
 * prove the Smart Wallet exposes the two capabilities the brief requires:
 * atomic batching and paymaster-sponsored gas. Phase 4 wires this through
 * to real onchain actions.
 */

export function PasskeyWallet() {
  const connection = useConnection();
  const { connect, isPending: connectPending, error: connectError } =
    useConnect();
  const { disconnect, isPending: disconnectPending } = useDisconnect();
  const connectors = useConnectors();

  const coinbaseConnector = useMemo(
    () => connectors.find((c) => c.id === "coinbaseWallet" || c.type === "coinbaseWallet"),
    [connectors],
  );

  const { data: caps, isLoading: capsLoading } = useCapabilities({
    account: connection.address,
    chainId: connection.chainId,
    query: { enabled: connection.status === "connected" },
  });

  // useCapabilities returns Record<chainId, Capabilities> when no chainId
  // is provided, or a single Capabilities object when chainId is. Type-narrow
  // by the param shape we passed.
  const summary = useMemo(
    () => summarizeCapabilities(caps as RawCapabilities | undefined),
    [caps],
  );

  if (connection.status === "connected" && connection.address) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-700 dark:text-zinc-300">
          Smart Wallet connected:{" "}
          <span className="font-mono text-zinc-900 dark:text-zinc-100">
            {truncateAddress(connection.address)}
          </span>
        </p>
        <CapabilityRow
          label="EIP-5792 atomic batch"
          ok={summary.batch}
          loading={capsLoading}
        />
        <CapabilityRow
          label="Paymaster-sponsored gas"
          ok={summary.paymaster}
          loading={capsLoading}
        />
        <button
          type="button"
          disabled={disconnectPending}
          onClick={() => disconnect()}
          className="tap self-start rounded-lg border border-zinc-300 px-4 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          {disconnectPending ? "Disconnecting..." : "Disconnect"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-zinc-700 dark:text-zinc-300">
        Connect a Coinbase Smart Wallet to monitor positions and (later) opt
        into Guardian Mode. Authentication is by Passkey; no seed phrase is
        ever generated or shown.
      </p>
      <button
        type="button"
        disabled={!coinbaseConnector || connectPending}
        onClick={() =>
          coinbaseConnector && connect({ connector: coinbaseConnector })
        }
        className="tap self-start rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-zinc-400"
      >
        {connectPending ? "Opening Passkey..." : "Connect Smart Wallet"}
      </button>
      {connectError ? (
        <p className="text-sm text-red-600 dark:text-red-400">
          {connectError.message}
        </p>
      ) : null}
    </div>
  );
}

function CapabilityRow({
  label,
  ok,
  loading,
}: {
  label: string;
  ok: boolean;
  loading: boolean;
}) {
  const dotClasses = loading
    ? "bg-zinc-300 dark:bg-zinc-700"
    : ok
    ? "bg-green-500"
    : "bg-red-500";
  const status = loading ? "checking" : ok ? "supported" : "not supported";
  return (
    <p className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
      <span className={`h-2 w-2 rounded-full ${dotClasses}`} aria-hidden />
      <span>{label}</span>
      <span className="text-xs text-zinc-500 dark:text-zinc-500">— {status}</span>
    </p>
  );
}
