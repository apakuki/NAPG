import { headers } from "next/headers";

import {
  formatTimestamp,
  isBreachFeedError,
  type BreachFeedError,
  type BreachFeedItem,
  type BreachFeedResponse,
} from "@/lib/breaches";

interface Props {
  source?: string;
  limit?: number;
}

/**
 * Server component that fetches the breach feed proxy at render time and
 * renders one row per breach. Live data is small (the audit log caps at 200
 * rows per request) so no client-side polling is needed; the page is
 * server-rendered and a manual refresh re-fetches.
 *
 * Per-row layout: severity dot, timestamp, source, rule, threshold vs
 * actual, message. Audit-log first; pretty UI second.
 */
export async function BreachFeed({ source, limit }: Props) {
  const hdrs = await headers();
  const host = hdrs.get("x-forwarded-host") ?? hdrs.get("host") ?? "localhost:3000";
  const proto = hdrs.get("x-forwarded-proto") ?? "http";
  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (limit) params.set("limit", String(limit));
  const qs = params.toString();
  const url = `${proto}://${host}/api/audit/breaches${qs ? `?${qs}` : ""}`;

  let body: BreachFeedResponse | BreachFeedError;
  try {
    const res = await fetch(url, { cache: "no-store" });
    body = (await res.json()) as BreachFeedResponse | BreachFeedError;
    if (!res.ok && !isBreachFeedError(body)) {
      body = { error: `proxy returned HTTP ${res.status}` };
    }
  } catch (err) {
    body = {
      error: err instanceof Error ? err.message : String(err),
    };
  }

  if (isBreachFeedError(body)) {
    return (
      <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
        <p className="font-semibold">Cannot reach the audit log</p>
        <p className="mt-1">{body.error}</p>
        <p className="mt-2 text-xs opacity-80">
          Start the agent with{" "}
          <code className="font-mono">scripts/start.sh</code> or set{" "}
          <code className="font-mono">NAPG_API_URL</code> to point at the
          running instance.
        </p>
      </div>
    );
  }

  if (body.items.length === 0) {
    return (
      <p className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
        No breaches recorded
        {source ? <> for source <code className="font-mono">{source}</code></> : null}
        . The audit log is the source of truth -- this is a healthy state, not a
        rendering bug.
      </p>
    );
  }

  return (
    <ul
      role="list"
      className="flex w-full flex-col divide-y divide-zinc-200 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-950"
    >
      {body.items.map((item) => (
        <BreachRow key={item.id} item={item} />
      ))}
    </ul>
  );
}

function BreachRow({ item }: { item: BreachFeedItem }) {
  const { payload } = item;
  const dot =
    payload.severity === "critical" ? "bg-red-500" : "bg-amber-500";
  return (
    <li className="flex flex-col gap-2 px-5 py-4 text-sm md:flex-row md:items-center md:gap-4">
      <span className="flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500 md:w-44">
        <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
        <span className="font-mono">{formatTimestamp(item.recorded_at)}</span>
      </span>
      <span className="text-xs uppercase tracking-wide text-zinc-500 md:w-24">
        {payload.source}
      </span>
      <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300 md:w-56">
        {payload.rule}
      </span>
      <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300 md:w-40">
        {String(payload.actual)} / {String(payload.threshold)}
      </span>
      <span className="flex-1 text-zinc-900 dark:text-zinc-100">
        {payload.message}
      </span>
    </li>
  );
}
