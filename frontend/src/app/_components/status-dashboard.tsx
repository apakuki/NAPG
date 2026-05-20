"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AerodromeCard,
  HeartbeatCard,
  MorphoCard,
  StatusResponse,
  isCardError,
} from "@/lib/status-types";

const POLL_INTERVAL_MS = 10_000;

type FetchState =
  | { kind: "loading"; data: null }
  | { kind: "ok"; data: StatusResponse; lastUpdated: number }
  | { kind: "error"; data: StatusResponse | null; error: string; lastUpdated: number | null };

export function StatusDashboard() {
  const [state, setState] = useState<FetchState>({ kind: "loading", data: null });
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const message =
          body && typeof body.error === "string" ? body.error : `HTTP ${res.status}`;
        setState((prev) => ({
          kind: "error",
          data: prev.kind === "ok" ? prev.data : prev.kind === "error" ? prev.data : null,
          error: message,
          lastUpdated:
            prev.kind === "ok"
              ? prev.lastUpdated
              : prev.kind === "error"
                ? prev.lastUpdated
                : null,
        }));
        return;
      }
      const data = (await res.json()) as StatusResponse;
      setState({ kind: "ok", data, lastUpdated: Date.now() });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState((prev) => ({
        kind: "error",
        data: prev.kind === "ok" ? prev.data : prev.kind === "error" ? prev.data : null,
        error: message,
        lastUpdated:
          prev.kind === "ok"
            ? prev.lastUpdated
            : prev.kind === "error"
              ? prev.lastUpdated
              : null,
      }));
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    // refresh() is async and only setState's inside its await chain, so this
    // is the "subscribe to external system" shape the lint rule allows in
    // spirit; the heuristic just can't tell.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    let timer: ReturnType<typeof setInterval> | null = setInterval(refresh, POLL_INTERVAL_MS);

    function onVisibilityChange() {
      if (document.hidden) {
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
      } else if (!timer) {
        void refresh();
        timer = setInterval(refresh, POLL_INTERVAL_MS);
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refresh]);

  const status = state.kind === "ok" || state.kind === "error" ? state.data : null;
  const lastUpdated = state.kind === "ok" ? state.lastUpdated : null;
  const transportError = state.kind === "error" ? state.error : null;

  return (
    <section className="flex w-full max-w-5xl flex-col gap-4">
      <header className="flex items-baseline justify-between text-sm text-zinc-500">
        <h2 className="text-base font-semibold text-zinc-700 dark:text-zinc-200">
          Live monitor state
        </h2>
        <span
          aria-live="polite"
          data-testid="last-updated"
          className="font-mono text-xs"
        >
          {lastUpdated
            ? `updated ${new Date(lastUpdated).toLocaleTimeString()}`
            : state.kind === "loading"
              ? "loading..."
              : "no data yet"}
        </span>
      </header>

      {transportError ? (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-200"
        >
          Cannot reach the agent API: <code className="font-mono">{transportError}</code>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <HeartbeatCardView card={status?.heartbeat ?? null} />
        <AerodromeCardView card={status?.aerodrome ?? null} />
        <MorphoCardView card={status?.morpho ?? null} />
      </div>
    </section>
  );
}

function CardShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <article className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">{title}</h3>
        {subtitle ? (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>
        ) : null}
      </header>
      <div className="text-sm">{children}</div>
    </article>
  );
}

function ErrorBody({ message }: { message: string }) {
  return (
    <p role="status" className="font-mono text-xs text-amber-700 dark:text-amber-400">
      {message}
    </p>
  );
}

function LoadingBody() {
  return <p className="text-xs text-zinc-400">loading...</p>;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2 py-0.5">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="font-mono text-xs text-zinc-800 dark:text-zinc-200">{value}</span>
    </div>
  );
}

function HeartbeatCardView({ card }: { card: HeartbeatCard | { error: string } | null }) {
  if (card === null) {
    return (
      <CardShell title="RPC heartbeat" subtitle="Base latency + reorg">
        <LoadingBody />
      </CardShell>
    );
  }
  if (isCardError(card)) {
    return (
      <CardShell title="RPC heartbeat" subtitle="Base latency + reorg">
        <ErrorBody message={card.error} />
      </CardShell>
    );
  }
  return (
    <CardShell
      title="RPC heartbeat"
      subtitle={`chain ${card.chain_id} via ${card.rpc_url}`}
    >
      <Row label="block" value={card.block.number.toLocaleString()} />
      <Row label="latency" value={`${card.latency_ms.toFixed(0)} ms`} />
      <Row
        label="reorg"
        value={
          card.reorg_detected ? (
            <span className="text-red-600 dark:text-red-400">detected</span>
          ) : (
            "none"
          )
        }
      />
    </CardShell>
  );
}

function AerodromeCardView({ card }: { card: AerodromeCard | { error: string } | null }) {
  if (card === null) {
    return (
      <CardShell title="Aerodrome USDC/USDT" subtitle="Peg deviation via 0x">
        <LoadingBody />
      </CardShell>
    );
  }
  if (isCardError(card)) {
    return (
      <CardShell title="Aerodrome USDC/USDT" subtitle="Peg deviation via 0x">
        <ErrorBody message={card.error} />
      </CardShell>
    );
  }
  return (
    <CardShell title="Aerodrome USDC/USDT" subtitle="Peg deviation via 0x">
      <Row
        label="quoted rate"
        value={card.quoted_rate !== null ? card.quoted_rate.toFixed(6) : "n/a"}
      />
      <Row
        label="peg deviation"
        value={
          card.peg_deviation_bps !== null ? `${card.peg_deviation_bps} bps` : "n/a"
        }
      />
      <Row
        label="sources"
        value={card.sources.length > 0 ? card.sources.join(", ") : "none"}
      />
      <Row label="latency" value={`${card.latency_ms.toFixed(0)} ms`} />
    </CardShell>
  );
}

function MorphoCardView({ card }: { card: MorphoCard | { error: string } | null }) {
  if (card === null) {
    return (
      <CardShell title="Morpho Blue" subtitle="WETH-USDC and cbBTC-USDC">
        <LoadingBody />
      </CardShell>
    );
  }
  if (isCardError(card)) {
    return (
      <CardShell title="Morpho Blue" subtitle="WETH-USDC and cbBTC-USDC">
        <ErrorBody message={card.error} />
      </CardShell>
    );
  }
  return (
    <CardShell title="Morpho Blue" subtitle={`block ${card.block_number.toLocaleString()}`}>
      {card.markets.map((m) => (
        <div key={m.market_id} className="mt-1 first:mt-0">
          <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
            {m.label}
          </p>
          <Row label="utilisation" value={`${(m.utilization_bps / 100).toFixed(2)}%`} />
          <Row label="staleness" value={`${m.staleness_seconds}s`} />
        </div>
      ))}
    </CardShell>
  );
}
