import { headers } from "next/headers";
import type { Metadata } from "next";

import { BreachFeed } from "../_components/breach-feed";
import { ShareToFarcaster } from "../_components/share-to-farcaster";
import { buildBreachFeedEmbed } from "@/lib/manifest";

export const dynamic = "force-dynamic";

async function resolveOrigin(): Promise<string> {
  const hdrs = await headers();
  const host = hdrs.get("x-forwarded-host") ?? hdrs.get("host") ?? "localhost:3000";
  const proto = hdrs.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}

export async function generateMetadata(): Promise<Metadata> {
  const origin = await resolveOrigin();
  return {
    title: "Breaches — NAPG",
    other: {
      "fc:miniapp": JSON.stringify(buildBreachFeedEmbed(origin)),
    },
    openGraph: {
      title: "NAPG Breach Feed",
      description: "Service Level Breaches across monitored Base protocols.",
      images: [`${origin}/opengraph-image`],
    },
  };
}

export default async function BreachesPage() {
  const origin = await resolveOrigin();
  return (
    <main className="flex min-h-screen flex-col items-center gap-6 bg-zinc-50 px-4 py-6 md:gap-8 md:px-6 md:py-10 dark:bg-black">
      <header className="flex w-full max-w-5xl flex-col gap-3 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Breach feed
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Service Level Breaches detected across the monitored protocols.
          Read directly from the append-only audit log; newest first.
        </p>
        <div className="flex justify-center">
          <ShareToFarcaster
            text="Latest Base protocol breaches via NAPG ↓"
            embedUrl={`${origin}/breaches`}
          />
        </div>
      </header>
      <section className="w-full max-w-5xl">
        <BreachFeed limit={50} />
      </section>
    </main>
  );
}
