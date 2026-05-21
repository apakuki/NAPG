"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type StartResponse = { channelToken: string; url: string };
type PollResponse =
  | { state: "pending" }
  | { state: "completed"; fid: number }
  | { state: "verification_failed"; reason: string }
  | { state: "unknown" };

type UiState =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "waiting"; channel: StartResponse }
  | { kind: "verifying" }
  | { kind: "error"; reason: string };

const POLL_INTERVAL_MS = 1500;

export function SignIn() {
  const [state, setState] = useState<UiState>({ kind: "idle" });
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const begin = useCallback(async () => {
    stopPolling();
    setState({ kind: "starting" });
    let channel: StartResponse;
    try {
      const res = await fetch("/api/auth/siwf/start", { method: "POST" });
      if (!res.ok) throw new Error(`relay responded HTTP ${res.status}`);
      channel = (await res.json()) as StartResponse;
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      setState({ kind: "error", reason });
      return;
    }
    setState({ kind: "waiting", channel });

    pollTimer.current = setInterval(async () => {
      let result: PollResponse;
      try {
        const res = await fetch(
          `/api/auth/siwf/poll?token=${encodeURIComponent(channel.channelToken)}`,
        );
        result = (await res.json()) as PollResponse;
      } catch {
        // Transient network errors: keep polling.
        return;
      }
      if (result.state === "pending") return;
      stopPolling();
      if (result.state === "completed") {
        setState({ kind: "verifying" });
        // Cookie is now set; reload so the server-rendered shell picks up the
        // session and re-renders this card as the signed-in view.
        window.location.reload();
        return;
      }
      const reason =
        result.state === "verification_failed"
          ? result.reason
          : "Sign-in expired or was never started. Please try again.";
      setState({ kind: "error", reason });
    }, POLL_INTERVAL_MS);
  }, [stopPolling]);

  if (state.kind === "waiting") {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-700 dark:text-zinc-300">
          Open this link in the Farcaster app to approve sign-in. We will pick
          it up automatically.
        </p>
        <a
          href={state.channel.url}
          className="tap break-all rounded-lg bg-blue-600 px-4 text-center text-sm font-medium text-white hover:bg-blue-700"
        >
          Open in Farcaster
        </a>
        <p className="text-xs text-zinc-500 dark:text-zinc-500">
          On desktop, copy the link to your phone or paste it into a QR
          generator. The channel expires after five minutes.
        </p>
        <button
          type="button"
          onClick={() => {
            stopPolling();
            setState({ kind: "idle" });
          }}
          className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
        >
          Cancel
        </button>
      </div>
    );
  }

  if (state.kind === "verifying") {
    return (
      <p className="text-sm text-zinc-700 dark:text-zinc-300">
        Verifying signature...
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        onClick={begin}
        disabled={state.kind === "starting"}
        className="tap rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-zinc-400"
      >
        {state.kind === "starting" ? "Opening channel..." : "Sign in with Farcaster"}
      </button>
      {state.kind === "error" ? (
        <p className="text-sm text-red-600 dark:text-red-400">{state.reason}</p>
      ) : null}
    </div>
  );
}
