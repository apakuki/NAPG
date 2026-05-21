import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildHomeEmbed, buildManifest } from "./manifest";

const ORIGIN = "https://napg.example";
let originalAssoc: string | undefined;

beforeEach(() => {
  originalAssoc = process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION;
  delete process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION;
});

afterEach(() => {
  if (originalAssoc === undefined) {
    delete process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION;
  } else {
    process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION = originalAssoc;
  }
});

describe("buildManifest", () => {
  it("includes every spec-required frame field", () => {
    const m = buildManifest(ORIGIN);
    expect(m.frame.version).toBe("1");
    expect(m.frame.name).toBeTruthy();
    expect(m.frame.homeUrl).toBe(`${ORIGIN}/`);
    expect(m.frame.iconUrl).toBe(`${ORIGIN}/api/og/icon-1024`);
    expect(m.frame.splashImageUrl).toBe(`${ORIGIN}/api/og/splash`);
    expect(m.frame.heroImageUrl).toBe(`${ORIGIN}/opengraph-image`);
  });

  it("honours the Farcaster Frame v2 string-length limits", () => {
    const m = buildManifest(ORIGIN);
    // Spec: name <= 32, subtitle <= 30 no emojis, description <= 170,
    // tags <= 5 of <= 20 chars each, canonicalDomain has no protocol.
    expect(m.frame.name.length).toBeLessThanOrEqual(32);
    expect(m.frame.subtitle.length).toBeLessThanOrEqual(30);
    expect(m.frame.subtitle).not.toMatch(/[\u{1F300}-\u{1FAFF}]/u);
    expect(m.frame.description.length).toBeLessThanOrEqual(170);
    expect(m.frame.tags.length).toBeLessThanOrEqual(5);
    for (const tag of m.frame.tags) {
      expect(tag.length).toBeLessThanOrEqual(20);
    }
    expect(m.frame.canonicalDomain).not.toMatch(/^https?:\/\//);
  });

  it("targets Base mainnet + Sepolia via CAIP-2 ids", () => {
    const m = buildManifest(ORIGIN);
    expect(m.frame.requiredChains).toContain("eip155:8453");
    expect(m.frame.requiredChains).toContain("eip155:84532");
  });

  it("omits accountAssociation when the env var is unset", () => {
    const m = buildManifest(ORIGIN);
    expect(m.accountAssociation).toBeUndefined();
  });

  it("attaches accountAssociation when the env var carries a valid triplet", () => {
    process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION = JSON.stringify({
      header: "h-base64",
      payload: "p-base64",
      signature: "s-base64",
    });
    const m = buildManifest(ORIGIN);
    expect(m.accountAssociation).toEqual({
      header: "h-base64",
      payload: "p-base64",
      signature: "s-base64",
    });
  });

  it("ignores malformed accountAssociation rather than crashing", () => {
    process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION = "not-json";
    expect(() => buildManifest(ORIGIN)).not.toThrow();
    expect(buildManifest(ORIGIN).accountAssociation).toBeUndefined();
  });

  it("ignores accountAssociation missing a required field", () => {
    process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION = JSON.stringify({
      header: "h",
      payload: "p",
      // signature missing
    });
    expect(buildManifest(ORIGIN).accountAssociation).toBeUndefined();
  });
});

describe("buildHomeEmbed", () => {
  it("uses launch_frame action with the home URL + splash assets", () => {
    const embed = buildHomeEmbed(ORIGIN);
    expect(embed.version).toBe("1");
    expect(embed.imageUrl).toBe(`${ORIGIN}/opengraph-image`);
    expect(embed.button.action.type).toBe("launch_frame");
    expect(embed.button.action.url).toBe(`${ORIGIN}/`);
    expect(embed.button.action.splashImageUrl).toBe(`${ORIGIN}/api/og/splash`);
  });

  it("respects the title <= 32 chars limit", () => {
    const embed = buildHomeEmbed(ORIGIN);
    expect(embed.button.title.length).toBeLessThanOrEqual(32);
  });
});
