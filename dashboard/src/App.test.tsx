import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200 }),
  );
});

describe("App", () => {
  it("renders the four primary sections and the global search", async () => {
    render(<App />);
    for (const label of ["Overview", "Activity", "Projects", "Settings"]) {
      expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("searchbox", { name: "Search" })).toBeInTheDocument();
  });
});
