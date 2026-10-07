import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import IntakePage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  createKit: vi.fn(),
  getKit: vi.fn(),
}));

describe("Intake Page", () => {
  it("does not ask visitors for an access code", () => {
    render(<IntakePage />);

    expect(screen.queryByLabelText(/access code/i)).toBeNull();
    expect(screen.queryByText(/access code/i)).toBeNull();
  });
});
