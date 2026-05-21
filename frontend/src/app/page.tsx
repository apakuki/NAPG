import { headers } from "next/headers";
import type { Metadata } from "next";

import { StatusDashboard } from "./_components/status-dashboard";
import { buildHomeEmbed } from "@/lib/manifest";

export async function generateMetadata(): Promise<Metadata> {
  const hdrs = await headers();
  const host = hdrs.get("x-forwarded-host") ?? hdrs.get("host") ?? "localhost:3000";
  const proto = hdrs.get("x-forwarded-proto") ?? "http";
  const origin = `${proto}://${host}`;
  return {
    other: {
      // Farcaster Frame v2 embed: makes this URL shareable as a launch-frame
      // in Farcaster casts. Distinct from the catalog manifest at
      // /.well-known/farcaster.json -- this is per-page.
      "fc:miniapp": JSON.stringify(buildHomeEmbed(origin)),
    },
    openGraph: {
      title: "NetAssure Protocol Guardian",
      description: "NOC-level Service Assurance for Base.",
      images: [`${origin}/opengraph-image`],
    },
  };
}

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center gap-8 bg-zinc-50 px-6 py-10 dark:bg-black">
      <header className="flex max-w-5xl flex-col gap-2 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          NetAssure Protocol Guardian
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Service Assurance Dashboard — Base ecosystem monitor state, refreshed every 10
          seconds.
        </p>
      </header>
      <StatusDashboard />
    </main>
  );
}
