export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-8 dark:bg-black">
      <div className="flex max-w-2xl flex-col gap-6 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
          NetAssure Protocol Guardian
        </h1>
        <p className="text-lg leading-8 text-zinc-600 dark:text-zinc-400">
          NOC-level Protocol Service Assurance for the Coinbase Base ecosystem.
        </p>
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          Phase 0 — scaffolding. Dashboard arrives in Phase 1.
        </p>
      </div>
    </main>
  );
}
