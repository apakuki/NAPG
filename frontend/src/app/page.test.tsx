import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("renders the NAPG name", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { name: /NetAssure Protocol Guardian/i })
    ).toBeInTheDocument();
  });
});
