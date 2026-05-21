/**
 * Brand-mark React tree used by every ImageResponse-driven image route
 * (favicon, icon-1024, splash, opengraph). Centralised so the icon, splash,
 * and OG card stay visually coherent without three near-duplicate JSX trees.
 *
 * Satori-renderable subset only: flexbox, no grid, no transforms, hex colors.
 */

import type { CSSProperties } from "react";

const NAPG_BLUE = "#2563EB";
const BG = "#0A0A0A";
const TEXT = "#F4F4F5";

export function BrandMark({
  size,
  caption,
  pad = 0.18,
}: {
  size: number;
  caption?: string;
  pad?: number;
}) {
  const padPx = Math.round(size * pad);
  const monogramFont = Math.round(size * 0.32);
  const captionFont = Math.max(14, Math.round(size * 0.04));
  const baseStyle: CSSProperties = {
    width: "100%",
    height: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    background: BG,
    color: TEXT,
    padding: padPx,
    fontFamily: '"Inter", "Helvetica", sans-serif',
  };
  return (
    <div style={baseStyle}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: monogramFont * 2.4,
          height: monogramFont * 2.4,
          borderRadius: monogramFont * 0.35,
          background: NAPG_BLUE,
          color: TEXT,
          fontSize: monogramFont,
          fontWeight: 700,
          letterSpacing: -2,
        }}
      >
        NAPG
      </div>
      {caption ? (
        <p
          style={{
            marginTop: padPx,
            fontSize: captionFont,
            color: TEXT,
            opacity: 0.85,
            textAlign: "center",
            maxWidth: size - padPx * 2,
            lineHeight: 1.2,
          }}
        >
          {caption}
        </p>
      ) : null}
    </div>
  );
}

export const NAPG_SPLASH_BG = BG;
