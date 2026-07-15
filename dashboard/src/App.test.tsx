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
  it("renders the dashboard navigation sections", async () => {
    render(<App />);
    for (const label of [
      "Overview",
      "Current Context",
      "Projects",
      "Memories",
      "Timeline",
      "Search",
      "Diagnostics",
      "Settings",
      "Preview Sync",
    ]) {
      expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
    }
  });
});
