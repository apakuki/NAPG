/**
 * Mini-app manifest construction. Lives in lib/ rather than the route handler
 * so we can unit-test the schema in isolation -- the route handler is then a
 * thin wrapper that just serves the JSON.
 *
 * Schema reference: https://miniapps.farcaster.xyz/docs/specification
 *
 * `accountAssociation` proves we control both the domain and a Farcaster
 * custody key. Generating it requires signing with that key, which we
 * cannot automate -- the user produces it via the Farcaster Manifest Tool
 * and pastes the signed triplet into NAPG_FARCASTER_ACCOUNT_ASSOCIATION as
 * a JSON string. Until that lands (Phase 3 sign-off / Phase 5 deploy), we
 * omit the field; base.dev will flag the manifest as unverified but the
 * Frame embed still renders.
 */

export interface AccountAssociation {
  header: string;
  payload: string;
  signature: string;
}

export interface FrameManifest {
  accountAssociation?: AccountAssociation;
  frame: {
    version: "1";
    name: string;
    homeUrl: string;
    iconUrl: string;
    splashImageUrl: string;
    splashBackgroundColor: string;
    heroImageUrl: string;
    subtitle: string;
    description: string;
    primaryCategory: string;
    tags: string[];
    requiredChains: string[];
    requiredCapabilities: string[];
    canonicalDomain: string;
  };
}

const NAME = "NetAssure Protocol Guardian";
const SUBTITLE = "Protocol Service Assurance";
const DESCRIPTION =
  "NOC-level Service Assurance for Base protocols. NAPG heartbeats Aerodrome and Morpho Blue, surfaces breaches, and migrates funds to a safe contract when SLOs break.";

export function buildManifest(origin: string): FrameManifest {
  const accountAssociation = parseAccountAssociation(
    process.env.NAPG_FARCASTER_ACCOUNT_ASSOCIATION,
  );
  const manifest: FrameManifest = {
    frame: {
      version: "1",
      name: NAME,
      homeUrl: `${origin}/`,
      iconUrl: `${origin}/api/og/icon-1024`,
      splashImageUrl: `${origin}/api/og/splash`,
      splashBackgroundColor: "#0a0a0a",
      heroImageUrl: `${origin}/opengraph-image`,
      subtitle: SUBTITLE,
      description: DESCRIPTION,
      primaryCategory: "finance",
      tags: ["defi", "monitoring", "base", "agent"],
      // CAIP-2 ids: Base mainnet + Base Sepolia.
      requiredChains: ["eip155:8453", "eip155:84532"],
      requiredCapabilities: ["wallet.getEthereumProvider"],
      canonicalDomain: stripProtocol(origin),
    },
  };
  if (accountAssociation) manifest.accountAssociation = accountAssociation;
  return manifest;
}

function parseAccountAssociation(
  raw: string | undefined,
): AccountAssociation | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AccountAssociation>;
    if (
      typeof parsed.header === "string" &&
      typeof parsed.payload === "string" &&
      typeof parsed.signature === "string"
    ) {
      return {
        header: parsed.header,
        payload: parsed.payload,
        signature: parsed.signature,
      };
    }
  } catch {
    // Malformed env var: skip rather than crash the manifest route.
  }
  return null;
}

function stripProtocol(origin: string): string {
  return origin.replace(/^https?:\/\//, "");
}

/**
 * Per-page Frame v2 embed (the `fc:miniapp` <meta>). Distinct from the
 * manifest above: the manifest describes the app to base.dev's catalog; the
 * embed makes a single URL shareable as a Frame in Farcaster casts. The
 * shapes overlap but are not identical.
 */
export interface FrameEmbed {
  version: "1";
  imageUrl: string;
  button: {
    title: string;
    action: {
      type: "launch_frame";
      url: string;
      name: string;
      splashImageUrl: string;
      splashBackgroundColor: string;
    };
  };
}

export function buildHomeEmbed(origin: string): FrameEmbed {
  return {
    version: "1",
    imageUrl: `${origin}/opengraph-image`,
    button: {
      title: "Open NAPG",
      action: {
        type: "launch_frame",
        url: `${origin}/`,
        name: NAME,
        splashImageUrl: `${origin}/api/og/splash`,
        splashBackgroundColor: "#0a0a0a",
      },
    },
  };
}
