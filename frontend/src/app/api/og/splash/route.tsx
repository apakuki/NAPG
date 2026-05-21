/**
 * Manifest splashImageUrl source: 200x200 PNG (per the Frame v2 spec).
 * Shown briefly when a user taps "Open NAPG" inside the Farcaster client
 * before the home URL finishes loading.
 */

import { ImageResponse } from "next/og";

import { BrandMark } from "@/app/_components/brand-mark";

export const runtime = "edge";

export async function GET() {
  return new ImageResponse(<BrandMark size={200} />, {
    width: 200,
    height: 200,
    headers: {
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
