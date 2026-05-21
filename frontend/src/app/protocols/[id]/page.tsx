import { headers } from "next/headers";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { BreachFeed } from "../../_components/breach-feed";
import { ShareToFarcaster } from "../../_components/share-to-farcaster";
import { BREACH_SOURCES, type BreachSource } from "@/lib/breaches";
import { buildProtocolEmbed } from "@/lib/manifest";

interface PageProps {
  params: Promise<{ id: string }>;
}

const PROTOCOL_LABELS: Record<BreachSource, { title: string; subtitle: string }> = {
  heartbeat: {
    title: "RPC Heartbeat",
    subtitle:
      "Base Sepolia + Base mainnet block height, latency, and reorg detection.",
  },
  aerodrome: {
    title: "Aerodrome USDC/USDT",
    subtitle: "Slipstream stable pool peg deviation and routed liquidity.",
  },
  morpho: {
    title: "Morpho Blue",
    subtitle:
      "WETH-USDC and cbBTC-USDC market utilisation and accrual staleness.",
  },
};

function isBreachSource(id: string): id is BreachSource {
  return (BREACH_SOURCES as readonly string[]).includes(id);
}

async function resolveOrigin(): Promise<string> {
  const hdrs = await headers();
  const host = hdrs.get("x-forwarded-host") ?? hdrs.get("host") ?? "localhost:3000";
  const proto = hdrs.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  if (!isBreachSource(id)) return {};
  const origin = await resolveOrigin();
  const labels = PROTOCOL_LABELS[id];
  return {
    title: `${labels.title} — NAPG`,
    other: {
      "fc:miniapp": JSON.stringify(buildProtocolEmbed(origin, id)),
    },
    openGraph: {
      title: `${labels.title} health — NAPG`,
      description: labels.subtitle,
      images: [`${origin}/opengraph-image`],
    },
  };
}

export default async function ProtocolDetailPage({ params }: PageProps) {
  const { id } = await params;
  if (!isBreachSource(id)) notFound();
  const labels = PROTOCOL_LABELS[id];
  const origin = await resolveOrigin();

  return (
    <main className="flex min-h-screen flex-col items-center gap-6 bg-zinc-50 px-4 py-6 md:gap-8 md:px-6 md:py-10 dark:bg-black">
      <header className="flex w-full max-w-5xl flex-col gap-2">
        <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
          Protocol
        </p>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
              {labels.title}
            </h1>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {labels.subtitle}
            </p>
          </div>
          <ShareToFarcaster
            text={`${labels.title} health from NAPG ↓`}
            embedUrl={`${origin}/protocols/${id}`}
          />
        </div>
      </header>
      <section
        aria-labelledby="breaches-heading"
        className="flex w-full max-w-5xl flex-col gap-4"
      >
        <h2
          id="breaches-heading"
          className="text-base font-semibold text-zinc-900 dark:text-zinc-100"
        >
          Recent breaches
        </h2>
        <BreachFeed source={id} limit={50} />
      </section>
    </main>
  );
}
