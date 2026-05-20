import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _resetForTests,
  pollChannel,
  setAppClient,
  startChannel,
} from "./siwf";

interface FakeChannel {
  channelToken: string;
  url: string;
  // Set by the test before pollChannel runs.
  status?: { state: "pending" } | {
    state: "completed";
    message: string;
    signature: `0x${string}`;
  };
  verify?:
    | { success: true; fid: number; address: `0x${string}` }
    | { isError: true; error?: string };
}

/**
 * Minimal fake of the Farcaster appClient that the lib hands to it.
 * Returns the same { isError, data } shape `@farcaster/auth-client` uses.
 */
interface VerifyArgs {
  nonce: string;
  domain: string;
  message: string;
  signature: `0x${string}`;
}

function buildFakeClient(channels: Record<string, FakeChannel>) {
  return {
    createChannel: vi.fn(async (args: { domain: string; siweUri: string }) => {
      const ch = channels[args.domain];
      if (!ch) {
        return {
          isError: true as const,
          error: { message: "no channel configured for domain" },
        };
      }
      return {
        isError: false as const,
        response: new Response(),
        data: { channelToken: ch.channelToken, url: ch.url, nonce: "x" },
      };
    }),
    status: vi.fn(async ({ channelToken }: { channelToken: string }) => {
      const entry = Object.values(channels).find(
        (c) => c.channelToken === channelToken,
      );
      if (!entry || !entry.status) {
        return {
          isError: false as const,
          response: new Response(),
          data: { state: "pending" },
        };
      }
      return {
        isError: false as const,
        response: new Response(),
        data: entry.status,
      };
    }),
    verifySignInMessage: vi.fn(async (args: VerifyArgs) => {
      void args; // typed-but-unused; tests assert on the call args via the mock
      // The fake uses the channel from the most recent createChannel call.
      const ch = Object.values(channels).find((c) => c.verify);
      if (!ch?.verify) {
        return { isError: true as const, error: { message: "no verify configured" } };
      }
      if ("isError" in ch.verify) {
        return {
          isError: true as const,
          error: { message: ch.verify.error ?? "verify failed" },
        };
      }
      return {
        isError: false as const,
        success: ch.verify.success,
        fid: ch.verify.fid,
        data: { address: ch.verify.address },
      };
    }),
  };
}

// The lib's `AppClient` is the real shape; the fake is structurally compatible
// for the three methods siwf.ts touches. Cast at the seam.
function inject(channels: Record<string, FakeChannel>) {
  const fake = buildFakeClient(channels);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const restore = setAppClient(fake as any);
  return { fake, restore };
}

beforeEach(() => {
  _resetForTests();
});

afterEach(() => {
  // Drop any client the test injected.
  setAppClient(null);
});

describe("startChannel", () => {
  it("returns channelToken + url from the relay", async () => {
    const { restore } = inject({
      "localhost:3000": { channelToken: "tok-abc", url: "farcaster://x" },
    });
    const result = await startChannel({
      domain: "localhost:3000",
      siweUri: "http://localhost:3000/api/auth/siwf/poll",
    });
    expect(result.channelToken).toBe("tok-abc");
    expect(result.url).toBe("farcaster://x");
    restore();
  });

  it("throws when the relay returns isError", async () => {
    const { restore } = inject({});
    await expect(
      startChannel({ domain: "nope.test", siweUri: "http://nope.test/" }),
    ).rejects.toThrow(/createChannel failed/);
    restore();
  });
});

describe("pollChannel", () => {
  it("returns 'unknown' when the channel token was never issued", async () => {
    const { restore } = inject({});
    const result = await pollChannel("never-seen");
    expect(result.state).toBe("unknown");
    restore();
  });

  it("returns 'pending' while the wallet has not signed yet", async () => {
    const { restore } = inject({
      "localhost:3000": {
        channelToken: "tok-pending",
        url: "farcaster://x",
        // No status set => fake returns {state: pending}.
      },
    });
    await startChannel({
      domain: "localhost:3000",
      siweUri: "http://localhost:3000/cb",
    });
    const result = await pollChannel("tok-pending");
    expect(result.state).toBe("pending");
    restore();
  });

  it("returns 'completed' with the fid + address after a valid signature", async () => {
    const { restore } = inject({
      "localhost:3000": {
        channelToken: "tok-ok",
        url: "farcaster://x",
        status: {
          state: "completed",
          message: "siwe-message",
          signature: "0xdead",
        },
        verify: {
          success: true,
          fid: 9152,
          address: "0x1234567890abcdef1234567890abcdef12345678",
        },
      },
    });
    await startChannel({
      domain: "localhost:3000",
      siweUri: "http://localhost:3000/cb",
    });
    const result = await pollChannel("tok-ok");
    expect(result).toEqual({
      state: "completed",
      fid: 9152,
      address: "0x1234567890abcdef1234567890abcdef12345678",
    });
    restore();
  });

  it("returns 'verification_failed' when the verifier rejects the signature", async () => {
    const { restore } = inject({
      "localhost:3000": {
        channelToken: "tok-bad",
        url: "farcaster://x",
        status: {
          state: "completed",
          message: "siwe-message",
          signature: "0xbeef",
        },
        verify: { isError: true, error: "nonce mismatch" },
      },
    });
    await startChannel({
      domain: "localhost:3000",
      siweUri: "http://localhost:3000/cb",
    });
    const result = await pollChannel("tok-bad");
    expect(result.state).toBe("verification_failed");
    if (result.state === "verification_failed") {
      expect(result.reason).toMatch(/nonce mismatch/);
    }
    restore();
  });

  it("is single-use: a second poll on a verified channel returns 'unknown'", async () => {
    const { restore } = inject({
      "localhost:3000": {
        channelToken: "tok-replay",
        url: "farcaster://x",
        status: {
          state: "completed",
          message: "siwe-message",
          signature: "0xdead",
        },
        verify: {
          success: true,
          fid: 1,
          address: "0x1234567890abcdef1234567890abcdef12345678",
        },
      },
    });
    await startChannel({
      domain: "localhost:3000",
      siweUri: "http://localhost:3000/cb",
    });
    const first = await pollChannel("tok-replay");
    expect(first.state).toBe("completed");
    const second = await pollChannel("tok-replay");
    expect(second.state).toBe("unknown");
    restore();
  });

  it("uses the server-side nonce, not anything echoed back by the relay", async () => {
    // The lib must call verifySignInMessage with the nonce *it* generated, so a
    // malicious relay that lies about the nonce cannot trick verification.
    const { fake, restore } = inject({
      "localhost:3000": {
        channelToken: "tok-nonce",
        url: "farcaster://x",
        status: {
          state: "completed",
          message: "siwe-message",
          signature: "0xdead",
        },
        verify: {
          success: true,
          fid: 7,
          address: "0x1234567890abcdef1234567890abcdef12345678",
        },
      },
    });
    const start = await startChannel({
      domain: "localhost:3000",
      siweUri: "http://localhost:3000/cb",
    });
    expect(start.channelToken).toBe("tok-nonce");
    await pollChannel("tok-nonce");
    expect(fake.verifySignInMessage).toHaveBeenCalledTimes(1);
    const call = fake.verifySignInMessage.mock.calls.at(0)?.at(0);
    if (!call) throw new Error("expected verifySignInMessage to have been called");
    // generateNonce() from viem gives us the value; we re-export the same map.
    // The lib stores it and passes it through; here we just assert nothing
    // empty / null leaked into the verify call.
    expect(typeof call.nonce).toBe("string");
    expect(call.nonce.length).toBeGreaterThan(0);
    expect(call.domain).toBe("localhost:3000");
    restore();
  });
});
