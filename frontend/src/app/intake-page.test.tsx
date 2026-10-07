import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import IntakePage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  createKit: vi.fn(),
  getKit: vi.fn(),
}));

describe("Intake Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not ask visitors for an access code", () => {
    render(<IntakePage />);

    expect(screen.queryByLabelText(/access code/i)).toBeNull();
    expect(screen.queryByText(/access code/i)).toBeNull();
  });

  it("offers only the paste-article input, with no URL option", () => {
    render(<IntakePage />);

    expect(screen.getByLabelText(/article text/i)).toBeTruthy();
    expect(screen.queryByLabelText(/url/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /article url/i })).toBeNull();
  });

  it("submits the pasted article text", async () => {
    const api = await import("@/lib/api");
    vi.mocked(api.createKit).mockResolvedValue({ kit_id: "k-1" });
    const article = "Pathos announced a new platform today. ".repeat(20);

    render(<IntakePage />);
    fireEvent.change(screen.getByLabelText(/article text/i), {
      target: { value: article },
    });
    fireEvent.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() =>
      expect(api.createKit).toHaveBeenCalledWith({ text: article.trim() })
    );
  });
});
