"use client";

import { useState } from "react";

export function SignOut() {
  const [pending, setPending] = useState(false);

  return (
    <button
      type="button"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        try {
          await fetch("/api/auth/signout", { method: "POST" });
        } finally {
          window.location.reload();
        }
      }}
      className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
    >
      {pending ? "Signing out..." : "Sign out"}
    </button>
  );
}
