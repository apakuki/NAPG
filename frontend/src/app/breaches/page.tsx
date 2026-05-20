export default function BreachesPage() {
  return (
    <main className="flex min-h-screen flex-col items-center gap-8 bg-zinc-50 px-6 py-10 dark:bg-black">
      <header className="flex max-w-5xl flex-col gap-2 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Breach feed
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Service Level Breaches detected across the monitored protocols.
        </p>
      </header>
      <section className="w-full max-w-5xl rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
        Scaffolding only. The audit-log-backed feed lands with the Phase 3
        substep that wires read-only audit queries into the FastAPI layer.
      </section>
    </main>
  );
}
