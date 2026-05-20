/**
 * Server-side Basenames reverse resolution: turn an Ethereum address into a
 * human-readable name like `samuel.base.eth`. Falls back to `null` whenever
 * the address has no primary name set, the RPC errors out, or the forward
 * verification doesn't match. Callers render a truncated address in that
 * case (graceful degrade per the Phase 3 troubleshooting playbook).
 *
 * Why we don't use viem's `getEnsName`: it routes through the chain's
 * `ensUniversalResolver` contract, which Base doesn't expose. Basenames
 * instead publishes a plain `ReverseRegistrar` + `L2Resolver` pair (see
 * https://github.com/base-org/basenames) so we go through those directly.
 *
 * The forward-verification step is critical: anyone can set a `name(node)`
 * record on a reverse node they own, so a trustless "address -> name" lookup
 * MUST resolve the candidate name back to an address and confirm it matches
 * the original. Without that check, a malicious user could set their reverse
 * record to `vitalik.base.eth` and we'd render that for them.
 *
 * In-memory cache: 5-minute TTL, single-instance. Fine for Phase 3 testnet;
 * Phase 5 replaces with a shared cache (Redis or similar) at mainnet cutover.
 */

import {
  createPublicClient,
  http,
  namehash,
  type Address,
  type Chain,
  type PublicClient,
} from "viem";
import { base } from "viem/chains";

// Canonical addresses from github.com/base-org/basenames (Base mainnet, 8453).
// Sepolia uses a different pair; we don't resolve names against testnet today.
const BASENAMES_RESOLVER: Address = "0xC6d566A56A1aFf6508b41f6c90ff131615583BCD";
const BASENAMES_REVERSE_REGISTRAR: Address =
  "0x79ea96012eea67a83431f1701b3dff7e37f9e282";

const REVERSE_REGISTRAR_ABI = [
  {
    name: "node",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "addr", type: "address" }],
    outputs: [{ name: "", type: "bytes32" }],
  },
] as const;

const RESOLVER_ABI = [
  {
    name: "name",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "node", type: "bytes32" }],
    outputs: [{ name: "", type: "string" }],
  },
  {
    name: "addr",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "node", type: "bytes32" }],
    outputs: [{ name: "", type: "address" }],
  },
] as const;

const CACHE_TTL_MS = 5 * 60 * 1000;
interface CacheEntry {
  name: string | null;
  cachedAt: number;
}
const cache = new Map<string, CacheEntry>();

let injectedClient: PublicClient | null = null;

function getClient(): PublicClient {
  if (injectedClient) return injectedClient;
  const rpcUrl = process.env.BASE_RPC_URL;
  if (!rpcUrl) {
    throw new Error(
      "BASE_RPC_URL is not set; cannot resolve Basenames against Base mainnet.",
    );
  }
  return createPublicClient({
    chain: base as Chain,
    transport: http(rpcUrl),
  }) as PublicClient;
}

/** Test-only: inject a stub PublicClient. Returns a restore handle. */
export function setBasenamesClient(client: PublicClient | null): () => void {
  const previous = injectedClient;
  injectedClient = client;
  return () => {
    injectedClient = previous;
  };
}

/** Test-only: drop the in-memory resolution cache. */
export function _resetCacheForTests(): void {
  cache.clear();
}

export async function resolveBasename(
  address: Address,
): Promise<string | null> {
  const key = address.toLowerCase();
  const now = Date.now();
  const cached = cache.get(key);
  if (cached && now - cached.cachedAt < CACHE_TTL_MS) {
    return cached.name;
  }

  let result: string | null = null;
  try {
    const client = getClient();
    const reverseNode = await client.readContract({
      address: BASENAMES_REVERSE_REGISTRAR,
      abi: REVERSE_REGISTRAR_ABI,
      functionName: "node",
      args: [address],
    });
    const name = await client.readContract({
      address: BASENAMES_RESOLVER,
      abi: RESOLVER_ABI,
      functionName: "name",
      args: [reverseNode],
    });
    if (name) {
      const forwardNode = namehash(name);
      const forwardAddr = await client.readContract({
        address: BASENAMES_RESOLVER,
        abi: RESOLVER_ABI,
        functionName: "addr",
        args: [forwardNode],
      });
      if (forwardAddr.toLowerCase() === key) {
        result = name;
      }
    }
  } catch {
    // RPC failure, ABI mismatch, no record -- all fall through to null.
    // Caller renders the truncated address as graceful degrade.
    result = null;
  }

  cache.set(key, { name: result, cachedAt: now });
  return result;
}

/** UI helper: render `0x1234...abcd` for an address that has no primary name. */
export function truncateAddress(address: string): string {
  if (address.length < 10) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}
