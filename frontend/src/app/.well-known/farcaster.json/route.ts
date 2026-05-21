/**
 * GET /.well-known/farcaster.json — serves the Base mini-app / Farcaster
 * Frame v2 manifest. Static enough that the response is cached for an hour
 * at the edge; bumping the manifest is a deliberate redeploy.
 *
 * Origin is derived per-request so the same code serves both
 * https://napg.example (prod) and http://localhost:3030 (dev) without
 * environment-specific build configuration.
 */

import { headers } from "next/headers";
import { NextResponse } from "next/server";

import { buildManifest } from "@/lib/manifest";

export const dynamic = "force-dynamic";

export async function GET() {
  const hdrs = await headers();
  const host = hdrs.get("x-forwarded-host") ?? hdrs.get("host");
  if (!host) {
    return NextResponse.json(
      { error: "no host header" },
      { status: 400 },
    );
  }
  const proto = hdrs.get("x-forwarded-proto") ?? "http";
  const origin = `${proto}://${host}`;
  return NextResponse.json(buildManifest(origin), {
    headers: {
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
