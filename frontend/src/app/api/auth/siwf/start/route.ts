/**
 * POST /api/auth/siwf/start — opens a Farcaster auth channel and returns the
 * deep-link URL the client renders so the user can complete sign-in inside
 * the Farcaster app. Body: empty. Response: `{ channelToken, url }`.
 *
 * Note on domain handling: SIWF binds the signed message to a specific domain
 * so a signature obtained for one app cannot be replayed against another. We
 * derive the domain from the request headers (`x-forwarded-host` first, then
 * `host`) rather than trusting any client-supplied value.
 *
 * Guarded by `applyGuards`: CSRF (Origin/Referer match) + per-IP rate
 * limit so an attacker can't open thousands of relay channels in a loop.
 */

import { headers } from "next/headers";
import { NextResponse } from "next/server";

import { startChannel } from "@/lib/siwf";
import { applyGuards } from "@/lib/api-guards";

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

export async function POST(request: Request) {
  const blocked = applyGuards(request, {
    bucketName: "siwf_start",
    csrf: true,
  });
  if (blocked) return blocked;

  const hdrs = await headers();
  const domain = resolveDomain(hdrs);
  const origin = resolveOrigin(hdrs, domain);
  const channel = await startChannel({ domain, siweUri: `${origin}/` });
  return NextResponse.json(channel);
}
