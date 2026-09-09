"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  createKit,
  getKit,
  getStoredAccessCode,
  setStoredAccessCode,
  KitDetail,
  KitStatus,
} from "@/lib/api";

export default function IntakePage() {
  const router = useRouter();

  // Mode: 'url' or 'paste'
  const [mode, setMode] = useState<"url" | "paste">("url");
  const [urlInput, setUrlInput] = useState("");
  const [textInput, setTextInput] = useState("");
  const [accessCode, setAccessCode] = useState("");

  // Pipeline execution state
  const [submitting, setSubmitting] = useState(false);
  const [activeKitId, setActiveKitId] = useState<string | null>(null);
  const [kitStatus, setKitStatus] = useState<KitStatus | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [thinContentNotice, setThinContentNotice] = useState<string | null>(null);

  // Load stored access code on mount
  useEffect(() => {
    const saved = getStoredAccessCode();
    if (saved) {
      setAccessCode(saved);
    }
  }, []);

  const handleAccessCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const code = e.target.value;
    setAccessCode(code);
    setStoredAccessCode(code);
  };

  const wordCount = textInput.trim()
    ? textInput.trim().split(/\s+/).length
    : 0;
  const charCount = textInput.length;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setThinContentNotice(null);

    if (mode === "url" && !urlInput.trim()) {
      setErrorMsg("Please enter a valid article URL.");
      return;
    }

    if (mode === "paste") {
      if (charCount < 500 && wordCount < 100) {
        setErrorMsg("Please paste full article text (minimum 500 characters).");
        return;
      }
    }

    setSubmitting(true);
    setKitStatus("extracting");

    try {
      const payload =
        mode === "url"
          ? { url: urlInput.trim() }
          : { text: textInput.trim() };

      const res = await createKit(payload);
      setActiveKitId(res.kit_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create kit";
      setErrorMsg(msg);
      setSubmitting(false);
      setKitStatus(null);
    }
  };

  // Poll kit progress
  useEffect(() => {
    if (!activeKitId) return;

    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const kit: KitDetail = await getKit(activeKitId);
        if (!isMounted) return;

        setKitStatus(kit.status);

        if (kit.status === "ready") {
          clearInterval(interval);
          setSubmitting(false);
          // Redirect to kit page
          router.push(`/kit/${kit.id}`);
        } else if (kit.status === "paste_pending") {
          clearInterval(interval);
          setSubmitting(false);
          setMode("paste");
          setThinContentNotice(
            "This URL could not be automatically extracted (paywall or dynamic JS). Please paste the article text directly below."
          );
        } else if (kit.status === "failed") {
          clearInterval(interval);
          setSubmitting(false);
          setErrorMsg(
            "Kit generation failed. You can inspect or resume it in the Library."
          );
        }
      } catch {
        // Continue polling
      }
    }, 1500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeKitId, router]);

  const stages: { key: KitStatus; label: string; desc: string }[] = [
    {
      key: "extracting",
      label: "1. Extraction",
      desc: "Extracting atomic source sentences and verifying quotes verbatim.",
    },
    {
      key: "generating",
      label: "2. Generation",
      desc: "Drafting 5 client-facing marketing assets citing source sentences.",
    },
    {
      key: "verifying",
      label: "3. Verification",
      desc: "Auditing claims against source quotes with programmatic checks.",
    },
    {
      key: "ready",
      label: "4. Ready",
      desc: "Complete activation kit ready for editing and clean copy export.",
    },
  ];

  const getStageIndex = (s: KitStatus | null): number => {
    if (!s) return -1;
    if (s === "extracting") return 0;
    if (s === "generating") return 1;
    if (s === "verifying") return 2;
    if (s === "ready") return 3;
    return 0;
  };

  const currentStageIndex = getStageIndex(kitStatus);

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      {/* Hero Header */}
      <div className="text-center mb-10">
        <span className="inline-block px-3 py-1 mb-3 text-xs font-semibold uppercase tracking-wider text-blue-700 bg-blue-50 border border-blue-200 rounded-full">
          Pay-on-Results PR Tooling
        </span>
        <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight sm:text-4xl">
          Coverage Activation, Not Reporting
        </h1>
        <p className="mt-3 text-base text-gray-600 max-w-xl mx-auto">
          Paste a published article URL or article text. Get 5 ready-to-use,
          client-facing marketing assets with every claim grounded in source
          quotes.
        </p>
      </div>

      {/* Access Code Gate Bar */}
      <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <label
            htmlFor="accessCodeInput"
            className="block text-xs font-semibold text-gray-700 uppercase tracking-wide"
          >
            Demo Access Code
          </label>
          <p className="text-xs text-gray-500">
            Passcode gates LLM endpoints against unauthorized abuse.
          </p>
        </div>
        <input
          id="accessCodeInput"
          type="password"
          value={accessCode}
          onChange={handleAccessCodeChange}
          placeholder="Enter access code"
          className="w-full sm:w-56 px-3 py-1.5 text-sm border border-gray-300 rounded bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      {/* Thin content redirect notice */}
      {thinContentNotice && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-sm flex items-start gap-3">
          <span className="text-lg">⚠️</span>
          <div>
            <p className="font-semibold mb-1">Direct Paste Mode Activated</p>
            <p>{thinContentNotice}</p>
          </div>
        </div>
      )}

      {/* Error notification */}
      {errorMsg && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-start justify-between">
          <span>{errorMsg}</span>
          <button
            onClick={() => setErrorMsg(null)}
            className="text-red-500 hover:text-red-700 font-bold ml-2"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Intake Form Card */}
      {!submitting && !activeKitId ? (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-gray-200 bg-gray-50/70">
            <button
              type="button"
              onClick={() => setMode("url")}
              className={`flex-1 py-3 text-sm font-semibold text-center border-b-2 transition ${
                mode === "url"
                  ? "border-blue-600 text-blue-700 bg-white"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              Article URL
            </button>
            <button
              type="button"
              onClick={() => setMode("paste")}
              className={`flex-1 py-3 text-sm font-semibold text-center border-b-2 transition ${
                mode === "paste"
                  ? "border-blue-600 text-blue-700 bg-white"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              Paste Article Text
            </button>
          </div>

          <form onSubmit={handleSubmit} className="p-6">
            {mode === "url" ? (
              <div>
                <label
                  htmlFor="urlInput"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Published Coverage URL
                </label>
                <input
                  id="urlInput"
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="https://techcrunch.com/2026/03/your-story"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  required
                />
                <p className="text-xs text-gray-500 mt-2">
                  Fetches article text with trafilatura. Paywalled or JS-rendered
                  pages automatically route to paste mode with zero stack traces.
                </p>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label
                    htmlFor="textInput"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Article Text Body
                  </label>
                  <span className="text-xs text-gray-400">
                    {charCount} characters ({wordCount} words)
                  </span>
                </div>
                <textarea
                  id="textInput"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="Paste the full article headline and body text here..."
                  rows={8}
                  className="w-full p-4 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-sans"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  Text entering the pipeline is hard-capped at 24,000 characters
                  (~6k tokens) to prevent context and wallet incidents.
                </p>
              </div>
            )}

            <div className="mt-6 flex items-center justify-between">
              <Link
                href="/library"
                className="text-xs font-semibold text-gray-500 hover:text-gray-800 transition"
              >
                View Library →
              </Link>
              <button
                type="submit"
                className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg text-sm shadow-sm transition"
              >
                Generate Activation Kit
              </button>
            </div>
          </form>
        </div>
      ) : (
        /* Active Pipeline Progress View */
        <div className="bg-white border border-gray-200 rounded-xl p-8 shadow-sm text-center">
          <div className="inline-block animate-spin rounded-full h-10 w-10 border-4 border-blue-600 border-t-transparent mb-6"></div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Generating Your Coverage Kit
          </h2>
          <p className="text-sm text-gray-500 mb-8">
            Target turnaround is under 90 seconds. We are extracting facts,
            generating multi-channel copy, and executing grounding checks.
          </p>

          {/* Stepper */}
          <div className="space-y-4 max-w-md mx-auto text-left">
            {stages.map((stage, idx) => {
              const isCurrent = currentStageIndex === idx;
              const isPast = currentStageIndex > idx;

              return (
                <div
                  key={stage.key}
                  className={`p-4 rounded-lg border transition ${
                    isCurrent
                      ? "border-blue-400 bg-blue-50/60"
                      : isPast
                      ? "border-green-300 bg-green-50/40"
                      : "border-gray-200 bg-gray-50/30 opacity-60"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                        isPast
                          ? "bg-green-600 text-white"
                          : isCurrent
                          ? "bg-blue-600 text-white animate-pulse"
                          : "bg-gray-300 text-gray-600"
                      }`}
                    >
                      {isPast ? "✓" : idx + 1}
                    </span>
                    <span className="font-semibold text-sm text-gray-800">
                      {stage.label}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 ml-9 mt-1">
                    {stage.desc}
                  </p>
                </div>
              );
            })}
          </div>

          {activeKitId && (
            <div className="mt-8 pt-6 border-t border-gray-100 flex items-center justify-center gap-4">
              <Link
                href={`/kit/${activeKitId}`}
                className="text-xs text-blue-600 hover:underline"
              >
                Go directly to kit view →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
