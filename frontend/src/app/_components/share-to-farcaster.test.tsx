import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ShareToFarcaster } from "./share-to-farcaster";

describe("ShareToFarcaster", () => {
  it("renders an anchor to farcaster.xyz/~/compose with the right text + embed", () => {
    render(
      <ShareToFarcaster
        text="check this out"
        embedUrl="https://napg.example/breaches"
      />,
    );
    const link = screen.getByRole("link", { name: /share to farcaster/i });
    const href = link.getAttribute("href") ?? "";
    expect(href.startsWith("https://farcaster.xyz/~/compose?")).toBe(true);
    expect(href).toContain("text=check+this+out");
    expect(href).toContain("embeds%5B%5D=");
    // Standard external-link guards.
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
