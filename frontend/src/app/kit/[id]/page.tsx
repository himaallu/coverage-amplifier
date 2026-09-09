"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  getKit,
  updateAsset,
  exportKit,
  resumeKit,
  KitDetail,
  AssetDetail,
  ClaimDetail,
} from "@/lib/api";
import { generateCleanExport } from "@/lib/export-clean";

const ASSET_LABELS: Record<string, string> = {
  linkedin_company: "LinkedIn Post — Company Voice",
  linkedin_founder: "LinkedIn Post — Founder Voice",
  instagram_caption: "Instagram Caption & Visual Direction",
  sales_blurb: "Sales Enablement Blurb",
  website_badge: 'Website "As Featured In" Badge',
};

export default function KitPage({ params }: { params: { id: string } }) {
  const kitId = params.id;
  const [kit, setKit] = useState<KitDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedAssetId, setCopiedAssetId] = useState<string | null>(null);
  const [editingAssetId, setEditingAssetId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [savingAssetId, setSavingAssetId] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);
  const [exportNotification, setExportNotification] = useState<string | null>(
    null
  );

  const fetchKitData = useCallback(async () => {
    try {
      const data = await getKit(kitId);
      setKit(data);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load coverage kit";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [kitId]);

  useEffect(() => {
    fetchKitData();
  }, [fetchKitData]);

  // Polling if still in progress
  useEffect(() => {
    if (!kit) return;
    const inProgress = ["extracting", "generating", "verifying"].includes(
      kit.status
    );
    if (!inProgress) return;

    const timer = setInterval(() => {
      fetchKitData();
    }, 2000);
    return () => clearInterval(timer);
  }, [kit, fetchKitData]);

  const handleCopyText = async (assetId: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedAssetId(assetId);
      setTimeout(() => setCopiedAssetId(null), 2000);
    } catch {
      alert("Failed to copy to clipboard.");
    }
  };

  const handleStartEdit = (asset: AssetDetail) => {
    setEditingAssetId(asset.id);
    setEditText(asset.text);
  };

  const handleCancelEdit = () => {
    setEditingAssetId(null);
    setEditText("");
  };

  const handleSaveEdit = async (assetId: string) => {
    if (!kit) return;
    setSavingAssetId(assetId);
    try {
      const updated = await updateAsset(kit.id, assetId, editText);
      setKit({
        ...kit,
        assets: kit.assets.map((a) => (a.id === assetId ? updated : a)),
      });
      setEditingAssetId(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to save edit: ${msg}`);
    } finally {
      setSavingAssetId(null);
    }
  };

  const handleResume = async () => {
    if (!kit) return;
    setResuming(true);
    try {
      await resumeKit(kit.id);
      fetchKitData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to resume kit: ${msg}`);
    } finally {
      setResuming(false);
    }
  };

  const handleDownloadExport = async (format: "markdown" | "html") => {
    if (!kit) return;
    try {
      const result = await exportKit(kit.id, format);
      const content =
        format === "markdown" ? result.markdown : result.html;
      const mime = format === "markdown" ? "text/markdown" : "text/html";
      const ext = format === "markdown" ? "md" : "html";

      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `kit-${kit.id.slice(0, 8)}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);

      setExportNotification(`Downloaded clean ${format.toUpperCase()} export!`);
      setTimeout(() => setExportNotification(null), 3000);
    } catch {
      // Fallback to client-side pure export
      const clientExport = generateCleanExport(kit);
      const content =
        format === "markdown" ? clientExport.markdown : clientExport.html;
      const blob = new Blob([content], {
        type: format === "markdown" ? "text/markdown" : "text/html",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `kit-${kit.id.slice(0, 8)}.${format === "markdown" ? "md" : "html"}`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  if (loading && !kit) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-12 text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
        <p className="text-gray-600">Loading coverage activation kit...</p>
      </div>
    );
  }

  if (error && !kit) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-lg">
          <h2 className="text-lg font-semibold mb-2">Error Loading Kit</h2>
          <p className="mb-4">{error}</p>
          <Link
            href="/library"
            className="text-sm font-medium text-red-800 underline"
          >
            ← Return to Library
          </Link>
        </div>
      </div>
    );
  }

  if (!kit) return null;

  // Compute pass rate & metrics
  const totalClaims = kit.assets.reduce(
    (acc, a) => acc + (a.claims ? a.claims.length : 0),
    0
  );
  const supportedClaims = kit.assets.reduce(
    (acc, a) =>
      acc +
      (a.claims
        ? a.claims.filter((c) => c.verdict === "supported").length
        : 0),
    0
  );

  const passRatePercent =
    kit.verification_run?.pass_rate !== undefined
      ? Math.round(kit.verification_run.pass_rate * 100)
      : totalClaims > 0
      ? Math.round((supportedClaims / totalClaims) * 100)
      : 100;

  const sourceIntegrityPercent =
    kit.source_integrity_rate !== null &&
    kit.source_integrity_rate !== undefined
      ? Math.round(kit.source_integrity_rate * 100)
      : 100;

  // Source sentence lookup
  const sourceSentenceMap = new Map<string, string>();
  (kit.source_sentences || []).forEach((s) => {
    sourceSentenceMap.set(s.id, s.text);
  });

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Back link */}
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/library"
          className="text-sm font-medium text-gray-500 hover:text-gray-800 transition-colors"
        >
          ← Back to Library
        </Link>
        <div className="flex gap-2">
          <button
            onClick={() => handleDownloadExport("markdown")}
            className="px-3 py-1.5 text-xs font-semibold rounded border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 shadow-sm transition"
          >
            Export Markdown
          </button>
          <button
            onClick={() => handleDownloadExport("html")}
            className="px-3 py-1.5 text-xs font-semibold rounded border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 shadow-sm transition"
          >
            Export HTML
          </button>
        </div>
      </div>

      {exportNotification && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-800 text-sm rounded-md animate-fade-in">
          {exportNotification}
        </div>
      )}

      {/* Kit Header & Grounding Summary */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm mb-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-gray-100 pb-6 mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider rounded bg-blue-50 text-blue-700 border border-blue-200">
                {kit.outlet || "Media Story"}
              </span>
              {kit.published_at && (
                <span className="text-xs text-gray-500">
                  {kit.published_at}
                </span>
              )}
            </div>
            <h1 className="text-2xl font-bold text-gray-900 leading-tight">
              {kit.title || "Coverage Activation Kit"}
            </h1>
            {kit.author && (
              <p className="text-xs text-gray-500 mt-1">By {kit.author}</p>
            )}
          </div>

          {/* Verification KPI Cards */}
          <div className="flex items-center gap-4">
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-center min-w-[130px]">
              <span className="block text-xs font-medium text-gray-500 uppercase tracking-wider">
                Kit Pass Rate
              </span>
              <span
                className={`text-2xl font-extrabold ${
                  passRatePercent >= 80
                    ? "text-green-600"
                    : passRatePercent >= 50
                    ? "text-amber-600"
                    : "text-red-600"
                }`}
              >
                {passRatePercent}%
              </span>
              <span className="block text-[10px] text-gray-400 mt-0.5">
                {supportedClaims} of {totalClaims} claims verified
              </span>
            </div>

            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-center min-w-[130px]">
              <span className="block text-xs font-medium text-gray-500 uppercase tracking-wider">
                Source Integrity
              </span>
              <span className="text-2xl font-extrabold text-blue-600">
                {sourceIntegrityPercent}%
              </span>
              <span className="block text-[10px] text-gray-400 mt-0.5">
                verbatim match vs article
              </span>
            </div>
          </div>
        </div>

        {/* Truncation warning if applicable */}
        {kit.truncated && (
          <div className="mb-4 text-xs bg-amber-50 text-amber-800 border border-amber-200 rounded p-2.5">
            Note: Source article exceeded 24,000 characters and was head-truncated
            to preserve key facts within the token guardrail.
          </div>
        )}

        {/* Pipeline state if in progress or failed */}
        {kit.status !== "ready" && (
          <div className="mt-4 p-4 rounded-lg bg-gray-50 border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium text-gray-700">
                  Status:{" "}
                  <span className="capitalize font-semibold text-blue-600">
                    {kit.status}
                  </span>
                </span>
                <p className="text-xs text-gray-500 mt-0.5">
                  {kit.status === "failed"
                    ? "Processing stalled or encountered an error."
                    : "Generating assets and verifying claims against source sentences..."}
                </p>
              </div>
              {kit.status === "failed" && (
                <button
                  onClick={handleResume}
                  disabled={resuming}
                  className="px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  {resuming ? "Resuming..." : "Resume Kit Pipeline"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Asset Cards Grid */}
      <div className="space-y-8">
        {kit.assets.map((asset) => {
          const isEditing = editingAssetId === asset.id;
          const isSaving = savingAssetId === asset.id;
          const label =
            ASSET_LABELS[asset.type] ||
            asset.type
              .replace(/_/g, " ")
              .replace(/\b\w/g, (c) => c.toUpperCase());

          return (
            <div
              key={asset.id}
              className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden"
            >
              {/* Card Header */}
              <div className="bg-gray-50/70 border-b border-gray-200 px-6 py-3 flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-800">
                  {label}
                </span>
                <div className="flex items-center gap-2">
                  {!isEditing ? (
                    <>
                      <button
                        onClick={() => handleStartEdit(asset)}
                        className="px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-gray-900 border border-gray-300 rounded bg-white hover:bg-gray-50 transition"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleCopyText(asset.id, asset.text)}
                        className="px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-gray-900 border border-gray-300 rounded bg-white hover:bg-gray-50 transition"
                      >
                        {copiedAssetId === asset.id ? "Copied!" : "Copy Clean Copy"}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => handleSaveEdit(asset.id)}
                        disabled={isSaving}
                        className="px-2.5 py-1 text-xs font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition"
                      >
                        {isSaving ? "Saving..." : "Save"}
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        disabled={isSaving}
                        className="px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-gray-800 border border-gray-300 rounded bg-white hover:bg-gray-50 transition"
                      >
                        Cancel
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Card Body: Clean Copy Display */}
              <div className="p-6">
                {isEditing ? (
                  <div>
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      rows={6}
                      className="w-full text-sm p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-sans"
                    />
                    <p className="text-[11px] text-gray-400 mt-1">
                      Edits update clean copy immediately. Citation markers and verification data are never injected.
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-gray-800 text-sm whitespace-pre-wrap leading-relaxed font-sans">
                      {asset.text}
                    </p>

                    {/* Meta specifics */}
                    {asset.type === "instagram_caption" && asset.meta && (
                      <div className="mt-4 pt-3 border-t border-gray-100 text-xs text-gray-600 space-y-1">
                        {Boolean(asset.meta.visual_direction) && (
                          <p>
                            <strong className="text-gray-700">
                              Visual Direction:
                            </strong>{" "}
                            {String(asset.meta.visual_direction)}
                          </p>
                        )}
                        {Array.isArray(asset.meta.hashtags) &&
                          asset.meta.hashtags.length > 0 && (
                            <p className="text-blue-600 font-mono text-[11px]">
                              {asset.meta.hashtags.join(" ")}
                            </p>
                          )}
                      </div>
                    )}

                    {asset.type === "website_badge" &&
                      Boolean(asset.meta?.html_snippet) && (
                        <div className="mt-4 pt-3 border-t border-gray-100">
                          <div className="mb-2 text-xs font-semibold text-gray-600">
                            HTML Snippet:
                          </div>
                          <pre className="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto">
                            <code>{String(asset.meta.html_snippet)}</code>
                          </pre>
                        </div>
                      )}
                  </div>
                )}

                {/* Verification Panel */}
                <div className="mt-6 pt-4 border-t border-gray-100">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
                      Factual Grounding & Verification Panel
                    </h3>
                    <span className="text-xs text-gray-400">
                      {asset.claims?.length || 0} claims audited
                    </span>
                  </div>

                  {asset.claims && asset.claims.length > 0 ? (
                    <div className="space-y-3">
                      {asset.claims.map((claim) => (
                        <ClaimRow
                          key={claim.id}
                          claim={claim}
                          sourceSentenceMap={sourceSentenceMap}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-400 italic">
                      No discrete factual claims requiring verification in this snippet.
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ClaimRow({
  claim,
  sourceSentenceMap,
}: {
  claim: ClaimDetail;
  sourceSentenceMap: Map<string, string>;
}) {
  const verdict = claim.verdict;

  let badgeColor = "bg-gray-100 text-gray-700 border-gray-200";
  let label = "Pending";

  if (verdict === "supported") {
    badgeColor = "bg-green-50 text-green-700 border-green-200";
    label = "Supported";
  } else if (verdict === "partial") {
    badgeColor = "bg-amber-50 text-amber-700 border-amber-200";
    label = "Partial";
  } else if (verdict === "unsupported") {
    badgeColor = "bg-red-50 text-red-700 border-red-200";
    label = "Unsupported";
  }

  return (
    <div className="bg-gray-50/60 border border-gray-200/80 rounded-lg p-3 text-xs">
      <div className="flex items-start justify-between gap-3 mb-1.5">
        <div className="font-medium text-gray-800">
          &ldquo;{claim.text_span}&rdquo;
        </div>
        <span
          className={`px-2 py-0.5 text-[11px] font-semibold rounded border uppercase tracking-wider shrink-0 ${badgeColor}`}
        >
          {label}
        </span>
      </div>

      {/* Quoted Source Sentences */}
      <div className="mt-2 space-y-1">
        {claim.source_ids && claim.source_ids.length > 0 ? (
          claim.source_ids.map((sid) => {
            const sentenceText = sourceSentenceMap.get(sid);
            return (
              <div key={sid} className="text-gray-600 pl-2 border-l-2 border-blue-400">
                <span className="font-mono font-semibold text-blue-700 text-[11px]">
                  {sid}:
                </span>{" "}
                {sentenceText ? (
                  <span>{sentenceText}</span>
                ) : (
                  <span className="text-red-500 italic">Source ID not found in article</span>
                )}
              </div>
            );
          })
        ) : (
          <div className="text-red-600 pl-2 border-l-2 border-red-400">
            No source citations provided for this factual claim.
          </div>
        )}
      </div>

      {claim.verifier_note && (
        <div className="mt-1.5 text-[11px] text-gray-500 italic">
          Note: {claim.verifier_note}
        </div>
      )}
    </div>
  );
}
