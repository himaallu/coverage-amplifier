"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { listKits, resumeKit, KitSummary } from "@/lib/api";

export default function LibraryPage() {
  const [kits, setKits] = useState<KitSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resumingKitId, setResumingKitId] = useState<string | null>(null);

  const loadKits = async () => {
    try {
      setLoading(true);
      const data = await listKits();
      setKits(data);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load kits from library";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKits();
  }, []);

  const handleResume = async (e: React.MouseEvent, kitId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setResumingKitId(kitId);
    try {
      await resumeKit(kitId);
      await loadKits();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to resume kit: ${msg}`);
    } finally {
      setResumingKitId(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 mb-8 border-b border-gray-200">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Activation Library
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Browse all past coverage activation kits, newest first.
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition"
        >
          + Create New Kit
        </Link>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
          <p className="text-gray-500 text-sm">Loading past kits...</p>
        </div>
      ) : kits.length === 0 ? (
        <div className="py-16 text-center border-2 border-dashed border-gray-200 rounded-xl bg-gray-50/50">
          <h3 className="text-base font-semibold text-gray-800 mb-1">
            No Coverage Kits Yet
          </h3>
          <p className="text-xs text-gray-500 max-w-sm mx-auto mb-6">
            Generate your first activation kit by pasting an article URL or text body.
          </p>
          <Link
            href="/"
            className="px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            Create Kit
          </Link>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="py-3.5 px-6">Story & Outlet</th>
                  <th className="py-3.5 px-4">Date</th>
                  <th className="py-3.5 px-4">Assets</th>
                  <th className="py-3.5 px-4">Verification Rate</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-6 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 text-sm">
                {kits.map((kit) => {
                  const passRate =
                    kit.verification_pass_rate !== null &&
                    kit.verification_pass_rate !== undefined
                      ? `${Math.round(kit.verification_pass_rate * 100)}%`
                      : "—";

                  const formattedDate = kit.published_at
                    ? kit.published_at
                    : new Date(kit.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      });

                  let statusBadge = "bg-gray-100 text-gray-700";
                  if (kit.status === "ready") {
                    statusBadge = "bg-green-50 text-green-700 border border-green-200";
                  } else if (kit.status === "failed") {
                    statusBadge = "bg-red-50 text-red-700 border border-red-200";
                  } else {
                    statusBadge = "bg-blue-50 text-blue-700 border border-blue-200 animate-pulse";
                  }

                  return (
                    <tr
                      key={kit.id}
                      className="hover:bg-gray-50/70 transition-colors group cursor-pointer"
                      onClick={() => (window.location.href = `/kit/${kit.id}`)}
                    >
                      <td className="py-4 px-6">
                        <div className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                          {kit.title || "Untitled Coverage Kit"}
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5 flex items-center gap-2">
                          <span className="font-medium text-gray-700">
                            {kit.outlet || "Unknown Outlet"}
                          </span>
                          {kit.truncated && (
                            <span className="text-[10px] bg-amber-100 text-amber-800 px-1 rounded">
                              truncated
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-4 px-4 text-xs text-gray-600 whitespace-nowrap">
                        {formattedDate}
                      </td>
                      <td className="py-4 px-4 text-xs text-gray-600 font-mono">
                        {kit.asset_count} assets
                      </td>
                      <td className="py-4 px-4 text-xs font-semibold whitespace-nowrap">
                        <span
                          className={
                            kit.verification_pass_rate &&
                            kit.verification_pass_rate >= 0.8
                              ? "text-green-600"
                              : kit.verification_pass_rate
                              ? "text-amber-600"
                              : "text-gray-400"
                          }
                        >
                          {passRate}
                        </span>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 text-[11px] font-semibold rounded capitalize ${statusBadge}`}
                        >
                          {kit.status}
                        </span>
                      </td>
                      <td className="py-4 px-6 text-right whitespace-nowrap">
                        {kit.status === "failed" ? (
                          <button
                            onClick={(e) => handleResume(e, kit.id)}
                            disabled={resumingKitId === kit.id}
                            className="px-2.5 py-1 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded transition disabled:opacity-50"
                          >
                            {resumingKitId === kit.id ? "Resuming..." : "Resume"}
                          </button>
                        ) : (
                          <Link
                            href={`/kit/${kit.id}`}
                            className="text-xs font-semibold text-blue-600 hover:text-blue-800 group-hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            View Kit →
                          </Link>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
