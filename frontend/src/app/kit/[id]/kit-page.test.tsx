import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import KitPage from "./page";
import { KitDetail } from "@/lib/api";

const mockKit: KitDetail = {
  id: "kit-1234-uuid",
  source_url: "https://example.com/pr-launch",
  outlet: "TechCrunch",
  title: "Pathos Revolutionizes PR Activation",
  author: "Sarah Connor",
  published_at: "2026-03-01",
  raw_text: "Full article text...",
  source_sentences: [
    {
      id: "S1",
      text: "Pathos announced an automated coverage activation kit.",
    },
    {
      id: "S2",
      text: "Revenue grew 45% in Q4 with high client retention.",
    },
  ],
  original_char_count: 5000,
  processed_char_count: 4800,
  truncated: false,
  source_integrity_rate: 1.0,
  status: "ready",
  created_at: "2026-03-01T12:00:00Z",
  verification_run: {
    id: "vr-1",
    pass_rate: 0.9,
    per_asset: {
      linkedin_company: 1.0,
      linkedin_founder: 1.0,
      instagram_caption: 0.8,
      sales_blurb: 1.0,
      website_badge: 1.0,
    },
    model_id: "gemini-pro",
    created_at: "2026-03-01T12:05:00Z",
  },
  assets: [
    {
      id: "a-1",
      kit_id: "kit-1234-uuid",
      type: "linkedin_company",
      text: "Excited to share that Pathos announced an automated coverage activation kit.",
      meta: { hashtags: ["#PR", "#Tech"] },
      created_at: "2026-03-01T12:01:00Z",
      claims: [
        {
          id: "c-1",
          text_span: "Pathos announced an automated coverage activation kit",
          source_ids: ["S1"],
          verdict: "supported",
          verifier_note: "Exact quote match",
        },
      ],
    },
    {
      id: "a-2",
      kit_id: "kit-1234-uuid",
      type: "linkedin_founder",
      text: "When we started Pathos, our goal was turning media wins into revenue.",
      meta: {},
      created_at: "2026-03-01T12:01:00Z",
      claims: [
        {
          id: "c-2",
          text_span: "turning media wins into revenue",
          source_ids: ["S1"],
          verdict: "partial",
          verifier_note: "Paraphrase of core mission",
        },
      ],
    },
    {
      id: "a-3",
      kit_id: "kit-1234-uuid",
      type: "instagram_caption",
      text: "Coverage activation in action. Press coverage that converts.",
      meta: {
        visual_direction: "High contrast screenshot with bold stat callout",
        hashtags: ["#PRTech", "#Growth"],
      },
      created_at: "2026-03-01T12:01:00Z",
      claims: [
        {
          id: "c-3",
          text_span: "Revenue grew 45% in Q4",
          source_ids: ["S2"],
          verdict: "supported",
          verifier_note: "Matches S2 stat",
        },
      ],
    },
    {
      id: "a-4",
      kit_id: "kit-1234-uuid",
      type: "sales_blurb",
      text: "Pathos reports 45% growth in Q4, validating the pay-on-results model for enterprise PR.",
      meta: {},
      created_at: "2026-03-01T12:01:00Z",
      claims: [
        {
          id: "c-4",
          text_span: "enterprise PR growth",
          source_ids: ["S2"],
          verdict: "unsupported",
          verifier_note: "Word enterprise not found in source article",
        },
      ],
    },
    {
      id: "a-5",
      kit_id: "kit-1234-uuid",
      type: "website_badge",
      text: '<a href="https://example.com/pr-launch">Featured on TechCrunch</a>',
      meta: {
        html_snippet:
          '<a href="https://example.com/pr-launch">Featured on TechCrunch</a>',
      },
      created_at: "2026-03-01T12:01:00Z",
      claims: [],
    },
  ],
};

// Mock the API client module
vi.mock("@/lib/api", () => ({
  getKit: vi.fn(),
  updateAsset: vi.fn(),
  exportKit: vi.fn(),
}));

describe("Kit Page & Verification Component Tests", () => {
  beforeEach(async () => {
    const api = await import("@/lib/api");
    vi.mocked(api.getKit).mockResolvedValue(mockKit);
    vi.mocked(api.exportKit).mockResolvedValue({
      markdown: "# Pathos Clean Copy\n\nExcited to share that Pathos announced...",
      html: "<h1>Pathos Clean Copy</h1><p>Excited to share that Pathos announced...</p>",
      title: "Pathos Revolutionizes PR Activation",
      outlet: "TechCrunch",
    });
  });

  it("renders all five asset types and verification summary stats", async () => {
    render(<KitPage params={{ id: "kit-1234-uuid" }} />);

    // Wait for kit to load
    await waitFor(() => {
      expect(
        screen.getByText("Pathos Revolutionizes PR Activation")
      ).toBeInTheDocument();
    });

    // Verification stats at top
    expect(screen.getByText(/90%/i)).toBeInTheDocument(); // Pass rate 90%
    expect(screen.getByText(/100%/i)).toBeInTheDocument(); // Source integrity 100%

    // 5 Asset Cards
    expect(screen.getByText(/LinkedIn Post — Company Voice/i)).toBeInTheDocument();
    expect(screen.getByText(/LinkedIn Post — Founder Voice/i)).toBeInTheDocument();
    expect(screen.getByText(/Instagram Caption/i)).toBeInTheDocument();
    expect(screen.getByText(/Sales Enablement Blurb/i)).toBeInTheDocument();
    expect(screen.getByText(/Website "As Featured In" Badge/i)).toBeInTheDocument();

    // Verify copy rendered
    expect(
      screen.getByText(
        /Excited to share that Pathos announced an automated coverage activation kit/i
      )
    ).toBeInTheDocument();
  });

  it("renders the verification panel with green/amber/red badges and quotes the cited source sentence", async () => {
    render(<KitPage params={{ id: "kit-1234-uuid" }} />);

    await waitFor(() => {
      expect(
        screen.getByText("Pathos Revolutionizes PR Activation")
      ).toBeInTheDocument();
    });

    // Supported badge (green)
    expect(screen.getAllByText(/Supported/i).length).toBeGreaterThan(0);
    // Partial badge (amber)
    expect(screen.getByText(/Partial/i)).toBeInTheDocument();
    // Unsupported badge (red)
    expect(screen.getByText(/Unsupported/i)).toBeInTheDocument();

    // The cited source sentence should be quoted alongside the flag
    expect(
      screen.getAllByText(/Pathos announced an automated coverage activation kit/i).length
    ).toBeGreaterThanOrEqual(2);
    expect(
      screen.getAllByText(/Revenue grew 45% in Q4 with high client retention/i).length
    ).toBeGreaterThanOrEqual(1);
  });

  it("asserts export purity: clean copy only, zero citation markers, zero verification verdicts", async () => {
    const { generateCleanExport } = await import("@/lib/export-clean");

    const exportText = generateCleanExport(mockKit);

    // Asset texts are present
    expect(exportText.markdown).toContain(
      "Excited to share that Pathos announced an automated coverage activation kit."
    );
    expect(exportText.markdown).toContain(
      "When we started Pathos, our goal was turning media wins into revenue."
    );

    // ZERO citation markers [S#]
    expect(exportText.markdown).not.toMatch(/\[S\d+\]/);
    expect(exportText.html).not.toMatch(/\[S\d+\]/);

    // ZERO verification verdicts or notes
    expect(exportText.markdown.toLowerCase()).not.toContain("supported");
    expect(exportText.markdown.toLowerCase()).not.toContain("partial");
    expect(exportText.markdown.toLowerCase()).not.toContain("unsupported");
    expect(exportText.markdown.toLowerCase()).not.toContain("verifier note");

    expect(exportText.html.toLowerCase()).not.toContain("supported");
    expect(exportText.html.toLowerCase()).not.toContain("partial");
    expect(exportText.html.toLowerCase()).not.toContain("unsupported");
  });
});
