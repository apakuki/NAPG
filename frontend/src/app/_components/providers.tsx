"use client";

/**
 * Client-side providers tree for the App Router. Sits in the root layout so
 * every page can call wagmi hooks. Both providers are intentionally client-
 * only because:
 *   - WagmiProvider uses React Context and the EIP-1193 provider, which only
 *     exists in the browser.
 *   - The Coinbase Smart Wallet popup is a window.open() call, not an SSR
 *     concept.
 *
 * The QueryClient is constructed once per browser session (lazy-initialised
 * via useState so it survives StrictMode double-renders without resetting
 * caches).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { WagmiProvider } from "wagmi";

import { wagmiConfig } from "@/lib/wagmi";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </WagmiProvider>
  );
}
