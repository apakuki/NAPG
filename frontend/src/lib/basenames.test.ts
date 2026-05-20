import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { namehash } from "viem";

import {
  _resetCacheForTests,
  resolveBasename,
  setBasenamesClient,
  truncateAddress,
} from "./basenames";

const REVERSE_REGISTRAR = "0x79ea96012eea67a83431f1701b3dff7e37f9e282";
const RESOLVER = "0xC6d566A56A1aFf6508b41f6c90ff131615583BCD";

const REVERSE_NODE =
  "0x0000000000000000000000000000000000000000000000000000000000001111";
const USER_ADDR = "0x1234567890abcdef1234567890abcdef12345678";

/**
 * Build a stub PublicClient whose `readContract` answers based on (address,
 * functionName) so each test can describe a deployed-contract scenario by
 * data rather than by mock-call-order.
 */
function stubClient(
  answers: Record<string, unknown>,
  options: { throwOn?: string } = {},
) {
  const readContract = vi.fn(
    async (args: { address: string; functionName: string }) => {
      const key = `${args.address.toLowerCase()}::${args.functionName}`;
      if (options.throwOn === key) {
        throw new Error(`stubbed transport failure on ${key}`);
      }
      if (!(key in answers)) {
        throw new Error(`unexpected readContract call: ${key}`);
      }
      return answers[key];
    },
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return { readContract } as any;
}

beforeEach(() => {
  _resetCacheForTests();
});

afterEach(() => {
  setBasenamesClient(null);
});

describe("resolveBasename", () => {
  it("returns the name when reverse + forward both check out", async () => {
    const name = "samuel.base.eth";
    const restore = setBasenamesClient(
      stubClient({
        [`${REVERSE_REGISTRAR}::node`]: REVERSE_NODE,
        [`${RESOLVER.toLowerCase()}::name`]: name,
        [`${RESOLVER.toLowerCase()}::addr`]: USER_ADDR,
      }),
    );
    const result = await resolveBasename(USER_ADDR);
    expect(result).toBe(name);
    restore();
  });

  it("returns null when forward resolution does not match the original address", async () => {
    // Classic squatter scenario: someone sets their reverse to vitalik.base.eth
    // hoping a credulous app will render that. The forward check defeats it.
    const restore = setBasenamesClient(
      stubClient({
        [`${REVERSE_REGISTRAR}::node`]: REVERSE_NODE,
        [`${RESOLVER.toLowerCase()}::name`]: "vitalik.base.eth",
        // namehash(vitalik.base.eth) resolves to someone else's address.
        [`${RESOLVER.toLowerCase()}::addr`]:
          "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
      }),
    );
    const result = await resolveBasename(USER_ADDR);
    expect(result).toBeNull();
    restore();
  });

  it("returns null when the resolver has no name record", async () => {
    const restore = setBasenamesClient(
      stubClient({
        [`${REVERSE_REGISTRAR}::node`]: REVERSE_NODE,
        [`${RESOLVER.toLowerCase()}::name`]: "",
      }),
    );
    const result = await resolveBasename(USER_ADDR);
    expect(result).toBeNull();
    restore();
  });

  it("returns null and does not throw when the RPC fails", async () => {
    const restore = setBasenamesClient(
      stubClient(
        {},
        { throwOn: `${REVERSE_REGISTRAR}::node` },
      ),
    );
    const result = await resolveBasename(USER_ADDR);
    expect(result).toBeNull();
    restore();
  });

  it("caches the result so a second lookup does not hit the RPC", async () => {
    const stub = stubClient({
      [`${REVERSE_REGISTRAR}::node`]: REVERSE_NODE,
      [`${RESOLVER.toLowerCase()}::name`]: "samuel.base.eth",
      [`${RESOLVER.toLowerCase()}::addr`]: USER_ADDR,
    });
    const restore = setBasenamesClient(stub);
    await resolveBasename(USER_ADDR);
    await resolveBasename(USER_ADDR);
    // First call: node + name + addr = 3 reads. Cached second call: 0 reads.
    expect(stub.readContract).toHaveBeenCalledTimes(3);
    restore();
  });

  it("caches the null result so failed lookups also short-circuit", async () => {
    const stub = stubClient(
      {},
      { throwOn: `${REVERSE_REGISTRAR}::node` },
    );
    const restore = setBasenamesClient(stub);
    await resolveBasename(USER_ADDR);
    await resolveBasename(USER_ADDR);
    expect(stub.readContract).toHaveBeenCalledTimes(1);
    restore();
  });

  it("uses lowercase address as the cache key (case-insensitive)", async () => {
    const stub = stubClient({
      [`${REVERSE_REGISTRAR}::node`]: REVERSE_NODE,
      [`${RESOLVER.toLowerCase()}::name`]: "samuel.base.eth",
      [`${RESOLVER.toLowerCase()}::addr`]: USER_ADDR,
    });
    const restore = setBasenamesClient(stub);
    await resolveBasename(USER_ADDR);
    const upper = ("0x" + USER_ADDR.slice(2).toUpperCase()) as `0x${string}`;
    await resolveBasename(upper);
    expect(stub.readContract).toHaveBeenCalledTimes(3);
    restore();
  });

  it("computes namehash for the forward verification (sanity check)", async () => {
    // Lock in that the forward verification uses ENSIP-1 namehash, not some
    // homegrown encoding. If viem's namehash changes shape we want to know.
    const name = "samuel.base.eth";
    const stub = stubClient({
      [`${REVERSE_REGISTRAR}::node`]: REVERSE_NODE,
      [`${RESOLVER.toLowerCase()}::name`]: name,
      [`${RESOLVER.toLowerCase()}::addr`]: USER_ADDR,
    });
    const restore = setBasenamesClient(stub);
    await resolveBasename(USER_ADDR);
    const addrCall = stub.readContract.mock.calls.find(
      (call: [{ functionName: string }]) => call[0].functionName === "addr",
    );
    expect(addrCall).toBeDefined();
    expect(addrCall?.[0].args).toEqual([namehash(name)]);
    restore();
  });
});

describe("truncateAddress", () => {
  it("renders the canonical short form", () => {
    expect(truncateAddress("0x1234567890abcdef1234567890abcdef12345678")).toBe(
      "0x1234...5678",
    );
  });

  it("passes through anything too short to truncate", () => {
    expect(truncateAddress("0x1234")).toBe("0x1234");
  });
});
