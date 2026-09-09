import { KitDetail } from "./api";

const ASSET_LABELS: Record<string, string> = {
  linkedin_company: "LinkedIn Post — Company Voice",
  linkedin_founder: "LinkedIn Post — Founder Voice",
  instagram_caption: "Instagram Caption & Visual Direction",
  sales_blurb: "Sales Enablement Blurb",
  website_badge: 'Website "As Featured In" Badge',
};

/**
 * Strips citation markers like [S1], [S1, S2] from copy to guarantee export purity.
 */
export function stripCitationMarkers(text: string): string {
  return text.replace(/\[S\d+(?:,\s*S\d+)*\]/g, "").trim();
}

/**
 * Generates pure clean copy in Markdown and HTML.
 * ZERO citation markers.
 * ZERO verification data.
 */
export function generateCleanExport(kit: KitDetail): {
  markdown: string;
  html: string;
} {
  const title = kit.title || "Coverage Activation Kit";
  const outlet = kit.outlet || "Media Coverage";
  const dateStr = kit.published_at || "Recent";

  // 1. Clean Markdown
  const mdLines: string[] = [
    `# ${title}`,
    `**Outlet:** ${outlet} | **Date:** ${dateStr}`,
    "",
    "---",
    "",
  ];

  // 2. Clean HTML
  const htmlSections: string[] = [];

  for (const asset of kit.assets) {
    const label =
      ASSET_LABELS[asset.type] ||
      asset.type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    const cleanText = stripCitationMarkers(asset.text);

    // Markdown
    mdLines.push(`## ${label}`);
    mdLines.push("");
    mdLines.push(cleanText);

    if (asset.type === "instagram_caption" && asset.meta) {
      if (asset.meta.visual_direction) {
        mdLines.push("");
        mdLines.push(`**Visual Direction:** ${String(asset.meta.visual_direction)}`);
      }
      if (Array.isArray(asset.meta.hashtags) && asset.meta.hashtags.length > 0) {
        mdLines.push("");
        mdLines.push(`**Hashtags:** ${asset.meta.hashtags.join(" ")}`);
      }
    } else if (asset.type === "website_badge" && asset.meta?.html_snippet) {
      if (asset.meta.html_snippet !== cleanText) {
        mdLines.push("");
        mdLines.push("```html");
        mdLines.push(String(asset.meta.html_snippet));
        mdLines.push("```");
      }
    }

    mdLines.push("");
    mdLines.push("---");
    mdLines.push("");

    // HTML section
    let extraHtml = "";
    if (asset.type === "instagram_caption" && asset.meta) {
      if (asset.meta.visual_direction) {
        extraHtml += `<p><em>Visual Direction:</em> ${escapeHtml(
          String(asset.meta.visual_direction)
        )}</p>`;
      }
      if (Array.isArray(asset.meta.hashtags) && asset.meta.hashtags.length > 0) {
        extraHtml += `<p><small>${escapeHtml(
          asset.meta.hashtags.join(" ")
        )}</small></p>`;
      }
    } else if (asset.type === "website_badge" && asset.meta?.html_snippet) {
      extraHtml += `<pre><code>${escapeHtml(
        String(asset.meta.html_snippet)
      )}</code></pre>`;
    }

    htmlSections.push(
      `<section style="margin-bottom: 2rem;">\n  <h2>${escapeHtml(
        label
      )}</h2>\n  <p>${escapeHtml(cleanText).replace(
        /\n/g,
        "<br>"
      )}</p>\n  ${extraHtml}\n</section>`
    );
  }

  const markdown = mdLines.join("\n").trim();
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(title)}</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #111; }
    h1 { border-bottom: 2px solid #eaeaea; padding-bottom: 8px; }
    h2 { color: #2563eb; margin-top: 1.5rem; }
    pre { background: #f4f4f5; padding: 12px; border-radius: 6px; overflow-x: auto; }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  <p><strong>Outlet:</strong> ${escapeHtml(outlet)} | <strong>Date:</strong> ${escapeHtml(dateStr)}</p>
  <hr>
  ${htmlSections.join("\n")}
</body>
</html>`;

  return { markdown, html };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
