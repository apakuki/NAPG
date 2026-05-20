import { StatusDashboard } from "./_components/status-dashboard";

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
