import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200 }),
  );
});

describe("App", () => {
  it("renders all six nav tabs", async () => {
    render(<App />);
    for (const label of [
      "Workspace",
      "Project Brain",
      "Personal Brain",
      "Timeline",
      "Project State",
      "Generate Context",
    ]) {
      expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
    }
  });
});
