/**
 * Manifest iconUrl source: 1024x1024 PNG with no transparency (per the Frame
 * v2 spec). Served at /api/og/icon-1024 so the manifest can reference an
 * absolute URL under our own origin. Cached for an hour at the edge.
 */

import { ImageResponse } from "next/og";

import { BrandMark } from "@/app/_components/brand-mark";

export const runtime = "edge";

export async function GET() {
  return new ImageResponse(<BrandMark size={1024} />, {
    width: 1024,
    height: 1024,
    headers: {
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
