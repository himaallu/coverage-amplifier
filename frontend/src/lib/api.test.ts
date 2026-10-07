import { describe, it, expect, vi, afterEach } from "vitest";
import { createKit } from "./api";

describe("API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("does not send an X-Access-Code header, even with a stale stored code", async () => {
    localStorage.setItem("coverage_amplifier_access_code", "old-code");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ kit_id: "k-1" }), { status: 202 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await createKit({ url: "https://example.com/article" });

    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.has("X-Access-Code")).toBe(false);
  });
});
