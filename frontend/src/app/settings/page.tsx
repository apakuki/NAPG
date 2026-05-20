import { cookies } from "next/headers";

import { SignIn } from "../_components/sign-in";
import { SignOut } from "../_components/sign-out";
import { getSessionFromCookies } from "@/lib/session";

export default async function SettingsPage() {
  const session = getSessionFromCookies(await cookies());

  return (
    <main className="flex min-h-screen flex-col items-center gap-8 bg-zinc-50 px-6 py-10 dark:bg-black">
      <header className="flex max-w-5xl flex-col gap-2 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Settings
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Signed-in identity, monitored positions, alert preferences.
        </p>
      </header>
      <section
        aria-labelledby="identity-heading"
        className="flex w-full max-w-5xl flex-col gap-4 rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2
          id="identity-heading"
          className="text-base font-semibold text-zinc-900 dark:text-zinc-100"
        >
          Identity
        </h2>
        {session ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              Signed in as Farcaster fid{" "}
              <span className="font-mono text-zinc-900 dark:text-zinc-100">
                {session.fid}
              </span>
              .
            </p>
            <SignOut />
          </div>
        ) : (
          <SignIn />
        )}
      </section>
    </main>
  );
}
