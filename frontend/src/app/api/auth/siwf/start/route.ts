/**
 * POST /api/auth/siwf/start — opens a Farcaster auth channel and returns the
 * deep-link URL the client renders so the user can complete sign-in inside
 * the Farcaster app. Body: empty. Response: `{ channelToken, url }`.
 *
 * Note on domain handling: SIWF binds the signed message to a specific domain
 * so a signature obtained for one app cannot be replayed against another. We
 * derive the domain from the request headers (`x-forwarded-host` first, then
 * `host`) rather than trusting any client-supplied value.
 */

import { headers } from "next/headers";
import { NextResponse } from "next/server";

import { startChannel } from "@/lib/siwf";

function resolveDomain(hdrs: Headers): string {
  const fwdHost = hdrs.get("x-forwarded-host");
  if (fwdHost) return fwdHost;
  const host = hdrs.get("host");
  if (host) return host;
  throw new Error("Cannot determine host: no Host or X-Forwarded-Host header");
}

function resolveOrigin(hdrs: Headers, domain: string): string {
  const proto = hdrs.get("x-forwarded-proto") ?? "http";
  return `${proto}://${domain}`;
}

export async function POST() {
  const hdrs = await headers();
  const domain = resolveDomain(hdrs);
  const origin = resolveOrigin(hdrs, domain);
  // The siweUri is the URL the Farcaster app shows the user in the sign-in
  // prompt. Point it at the app root, not the polling endpoint — the user is
  // approving sign-in to the *site*, not authorising one API call.
  const channel = await startChannel({ domain, siweUri: `${origin}/` });
  return NextResponse.json(channel);
}
