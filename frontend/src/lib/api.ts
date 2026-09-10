export type KitStatus =
  | "extracting"
  | "generating"
  | "verifying"
  | "ready"
  | "failed"
  | "paste_pending";

export type ClaimVerdict = "pending" | "supported" | "partial" | "unsupported";

export interface ClaimDetail {
  id: string;
  text_span: string;
  source_ids: string[];
  verdict: ClaimVerdict;
  verifier_note?: string | null;
}

export interface AssetDetail {
  id: string;
  kit_id: string;
  type: string;
  text: string;
  meta: Record<string, unknown>;
  created_at: string;
  claims: ClaimDetail[];
}

export interface VerificationRunDetail {
  id: string;
  pass_rate: number;
  per_asset: Record<string, unknown>;
  model_id: string;
  created_at: string;
}

export interface KitSummary {
  id: string;
  outlet?: string | null;
  title?: string | null;
  author?: string | null;
  published_at?: string | null;
  status: KitStatus;
  created_at: string;
  asset_count: number;
  verification_pass_rate?: number | null;
  source_integrity_rate?: number | null;
  truncated: boolean;
}

export interface KitDetail {
  id: string;
  source_url?: string | null;
  outlet?: string | null;
  title?: string | null;
  author?: string | null;
  published_at?: string | null;
  raw_text?: string | null;
  source_sentences: Array<{ id: string; text: string }>;
  original_char_count?: number | null;
  processed_char_count?: number | null;
  truncated: boolean;
  source_integrity_rate?: number | null;
  status: KitStatus;
  created_at: string;
  verification_run?: VerificationRunDetail | null;
  assets: AssetDetail[];
}

export interface ExportResult {
  markdown: string;
  html: string;
  outlet?: string | null;
  title?: string | null;
}

const ACCESS_CODE_STORAGE_KEY = "coverage_amplifier_access_code";

export function getStoredAccessCode(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(ACCESS_CODE_STORAGE_KEY) || "";
}

export function setStoredAccessCode(code: string): void {
  if (typeof window === "undefined") return;
  if (!code) {
    localStorage.removeItem(ACCESS_CODE_STORAGE_KEY);
  } else {
    localStorage.setItem(ACCESS_CODE_STORAGE_KEY, code.trim());
  }
}

function getBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  }
  return "http://localhost:8000";
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const accessCode = getStoredAccessCode();

  const headers = new Headers(options.headers || {});
  if (accessCode && !headers.has("X-Access-Code")) {
    headers.set("X-Access-Code", accessCode);
  }
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errMessage = `HTTP error ${res.status}`;
    try {
      const errorJson = await res.json();
      if (errorJson.detail) {
        errMessage =
          typeof errorJson.detail === "string"
            ? errorJson.detail
            : JSON.stringify(errorJson.detail);
      }
    } catch {
      // Use fallback
    }
    const error = new Error(errMessage);
    Object.assign(error, { status: res.status });
    throw error;
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

export async function createKit(payload: {
  url?: string;
  text?: string;
}): Promise<{ kit_id: string }> {
  return request<{ kit_id: string }>("/api/kits", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listKits(): Promise<KitSummary[]> {
  return request<KitSummary[]>("/api/kits", {
    method: "GET",
  });
}

export async function getKit(kitId: string): Promise<KitDetail> {
  return request<KitDetail>(`/api/kits/${kitId}`, {
    method: "GET",
  });
}

export async function deleteKit(kitId: string): Promise<void> {
  return request<void>(`/api/kits/${kitId}`, {
    method: "DELETE",
  });
}

export async function updateAsset(
  kitId: string,
  assetId: string,
  text: string
): Promise<AssetDetail> {
  return request<AssetDetail>(`/api/kits/${kitId}/assets/${assetId}`, {
    method: "PATCH",
    body: JSON.stringify({ text }),
  });
}

export async function exportKit(
  kitId: string,
  format?: "markdown" | "html"
): Promise<ExportResult> {
  const query = format ? `?format=${format}` : "";
  return request<ExportResult>(`/api/kits/${kitId}/export${query}`, {
    method: "GET",
  });
}

export async function resumeKit(
  kitId: string
): Promise<{ kit_id: string; status: string }> {
  return request<{ kit_id: string; status: string }>(
    `/api/kits/${kitId}/resume`,
    {
      method: "POST",
    }
  );
}
