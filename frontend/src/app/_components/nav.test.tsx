import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Nav } from "./nav";

describe("Nav", () => {
  it("renders the three Phase 3 routes", () => {
    render(<Nav />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("link", { name: "Breaches" })).toHaveAttribute(
      "href",
      "/breaches",
    );
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });
});
