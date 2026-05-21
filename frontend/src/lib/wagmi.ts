/**
 * wagmi config for NAPG. Single Coinbase Smart Wallet connector forced via
 * `preference.options: 'smartWalletOnly'` so the user is funneled into a
 * Passkey-backed smart account -- no mnemonic recovery path, period (per the
 * Phase 3 security baseline).
 *
 * Chains: Base mainnet for Basenames lookups + production wallet use; Base
 * Sepolia for testnet flows. Both ride the public Base RPCs by default; pin
 * to a paid endpoint via env when we get rate-limited.
 *
 * Lives in a separate module so server components can import the same type
 * (e.g. for `wallet_getCapabilities` decoders) without dragging in the
 * React provider tree.
 */

import { http, createConfig } from "wagmi";
import { base, baseSepolia } from "wagmi/chains";
import { coinbaseWallet } from "wagmi/connectors";

export const wagmiConfig = createConfig({
  chains: [base, baseSepolia],
  connectors: [
    coinbaseWallet({
      appName: "NetAssure Protocol Guardian",
      preference: { options: "smartWalletOnly" },
    }),
  ],
  transports: {
    [base.id]: http(process.env.NEXT_PUBLIC_BASE_RPC_URL),
    [baseSepolia.id]: http(process.env.NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL),
  },
  // SSR-safe: tells wagmi we render on the server first, then hydrate.
  ssr: true,
});
