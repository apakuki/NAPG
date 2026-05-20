import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import Home from "./page";

describe("Home", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 200 })),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the NAPG name and dashboard heading", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { name: /NetAssure Protocol Guardian/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /live monitor state/i })).toBeInTheDocument();
  });
});
