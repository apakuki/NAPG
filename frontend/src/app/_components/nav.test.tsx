import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

let mockPathname = "/";

import { Nav } from "./nav";

afterEach(() => {
  mockPathname = "/";
});

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

  it("marks the active route with aria-current=page", () => {
    mockPathname = "/breaches";
    render(<Nav />);
    expect(screen.getByRole("link", { name: "Breaches" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("treats nested routes as active for their parent (e.g. /protocols/foo activates Breaches sibling? no)", () => {
    // Subroutes count as active for their own prefix, but not for unrelated
    // siblings. /protocols/heartbeat is not under /breaches, so Breaches
    // stays inactive.
    mockPathname = "/protocols/heartbeat";
    render(<Nav />);
    expect(screen.getByRole("link", { name: "Breaches" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});
