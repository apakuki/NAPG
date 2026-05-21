import { BreachFeed } from "../_components/breach-feed";

export const dynamic = "force-dynamic";

export default function BreachesPage() {
  return (
    <main className="flex min-h-screen flex-col items-center gap-8 bg-zinc-50 px-6 py-10 dark:bg-black">
      <header className="flex w-full max-w-5xl flex-col gap-2 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Breach feed
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Service Level Breaches detected across the monitored protocols.
          Read directly from the append-only audit log; newest first.
        </p>
      </header>
      <section className="w-full max-w-5xl">
        <BreachFeed limit={50} />
      </section>
    </main>
  );
}
