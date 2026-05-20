/**
 * Server-side wrapper around `@farcaster/auth-client` for SIWF.
 *
 * Three operations the API routes need:
 *   - `startChannel`  -> create a Farcaster auth channel for the client to render
 *   - `pollChannel`   -> check the relay for completion + verify the signature
 *   - (sign-out lives in `lib/session.ts`; nothing to do with Farcaster)
 *
 * State: a single in-memory `Map<channelToken, { nonce, domain, createdAt }>`.
 * The nonce we sent the relay must be matched against the message the wallet
 * signs (replay defence); we cannot rely on the relay echo alone because the
 * relay could be lying. The map self-purges entries older than 5 minutes on
 * every call. This is single-instance state — fine for Phase 3 testnet; Phase
 * 5 replaces it with a shared store (Redis or similar) at mainnet cutover.
 *
 * Caller injects a fake `appClient` in tests via `setAppClient`; the default
 * goes to the hosted Farcaster relay.
 */

import {
  createAppClient,
  generateNonce,
  viemConnector,
} from "@farcaster/auth-client";

type AppClient = ReturnType<typeof createAppClient>;

interface PendingChannel {
  nonce: string;
  domain: string;
  createdAt: number;
}

const CHANNEL_TTL_MS = 5 * 60 * 1000;
const pendingChannels: Map<string, PendingChannel> = new Map();

let injectedAppClient: AppClient | null = null;

function getAppClient(): AppClient {
  if (injectedAppClient) return injectedAppClient;
  return createAppClient({ ethereum: viemConnector() });
}

/** Replace the live appClient with a test double. Returns a restore handle. */
export function setAppClient(client: AppClient | null): () => void {
  const previous = injectedAppClient;
  injectedAppClient = client;
  return () => {
    injectedAppClient = previous;
  };
}

function purgeStale(now: number): void {
  for (const [token, info] of pendingChannels) {
    if (now - info.createdAt > CHANNEL_TTL_MS) {
      pendingChannels.delete(token);
    }
  }
}

export interface StartChannelArgs {
  domain: string;
  siweUri: string;
}

export interface StartChannelResult {
  channelToken: string;
  url: string;
}

export async function startChannel(args: StartChannelArgs): Promise<StartChannelResult> {
  const now = Date.now();
  purgeStale(now);

  const nonce = generateNonce();
  const result = await getAppClient().createChannel({
    siweUri: args.siweUri,
    domain: args.domain,
    nonce,
  });
  if (result.isError) {
    throw new Error(
      `Farcaster relay createChannel failed: ${result.error?.message ?? "unknown error"}`,
    );
  }
  pendingChannels.set(result.data.channelToken, {
    nonce,
    domain: args.domain,
    createdAt: now,
  });
  return { channelToken: result.data.channelToken, url: result.data.url };
}

export type PollResult =
  | { state: "unknown" }
  | { state: "pending" }
  | { state: "verification_failed"; reason: string }
  | { state: "completed"; fid: number; address: `0x${string}` };

export async function pollChannel(channelToken: string): Promise<PollResult> {
  const info = pendingChannels.get(channelToken);
  if (!info) return { state: "unknown" };

  const statusResult = await getAppClient().status({ channelToken });
  if (statusResult.isError) {
    // Transient relay error — leave the channel pending so the client can retry.
    return { state: "pending" };
  }
  const data = statusResult.data;
  if (data.state !== "completed" || !data.message || !data.signature) {
    return { state: "pending" };
  }

  const verifyResult = await getAppClient().verifySignInMessage({
    nonce: info.nonce,
    domain: info.domain,
    message: data.message,
    signature: data.signature as `0x${string}`,
  });
  // Channel is single-use whether verification succeeded or failed; clearing
  // the entry after the verify call is the replay defence.
  pendingChannels.delete(channelToken);
  if (verifyResult.isError) {
    return {
      state: "verification_failed",
      reason: verifyResult.error?.message ?? "signature verification failed",
    };
  }
  if (!verifyResult.success || verifyResult.fid == null) {
    return {
      state: "verification_failed",
      reason: "verifier returned success=false",
    };
  }
  // `data.address` is the Ethereum address that produced the signature
  // (custody or authAddress depending on authMethod). The relay cannot fake
  // it — it has to match the recovered signer, which `verifySignInMessage`
  // has just checked. Safe to seal into the session as the canonical address.
  const address = verifyResult.data.address as `0x${string}`;
  return { state: "completed", fid: Number(verifyResult.fid), address };
}

/** Test-only: drop the in-memory channel cache. */
export function _resetForTests(): void {
  pendingChannels.clear();
}
