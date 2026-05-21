import { ImageResponse } from "next/og";

import { BrandMark } from "./_components/brand-mark";

export const alt = "NetAssure Protocol Guardian";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <BrandMark
        size={630}
        caption="NOC-level Service Assurance for Base"
        pad={0.12}
      />
    ),
    size,
  );
}
