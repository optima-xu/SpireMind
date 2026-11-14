import type {
  BridgeProbeResult,
  LlmProbeResult,
  PolicyMode,
  RunDetailPayload,
  RunSummaryItem,
  SessionSnapshot,
  SettingsPayload,
} from "../types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      message = typeof detail === "string" ? detail : JSON.stringify(detail);
    } else if (typeof parsed === "string" && parsed) {
      message = parsed;
    }
    throw new Error(message);
  }
  return parsed as T;
}

export const api = {
  getHealth: () =>
    requestJson<{ ok: boolean; version: string; status: string; attempt_id: string | null }>(
      "/api/health",
    ),

  getSession: () => requestJson<SessionSnapshot>("/api/session"),

  startRun: (payload: { character?: string | null; ascension?: number | null; policy: PolicyMode }) =>
    requestJson<{ attempt_id: string; status: string; policy: PolicyMode; run_mode: string }>(
      "/api/session/start",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),

  attachRun: (payload: { policy: PolicyMode }) =>
    requestJson<{ attempt_id: string; status: string; policy: PolicyMode; run_mode: string }>(
      "/api/session/attach",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),

  pauseRun: () =>
    requestJson<{ status: string; attempt_id: string | null }>("/api/session/pause", {
      method: "POST",
    }),

  resumeRun: () =>
    requestJson<{ status: string; attempt_id: string | null }>("/api/session/resume", {
      method: "POST",
    }),

  stepOnce: (policy?: PolicyMode | null) =>
    requestJson<{ result: Record<string, unknown>; snapshot: SessionSnapshot }>("/api/session/step", {
      method: "POST",
      body: JSON.stringify({ policy: policy ?? null }),
    }),

  stopRun: () =>
    requestJson<{ status: string; attempt_id: string | null }>("/api/session/stop", {
      method: "POST",
    }),

  observeBridge: () => requestJson<SessionSnapshot>("/api/bridge/observe"),

  getSettings: () => requestJson<SettingsPayload>("/api/settings"),

  updateSettings: (payload: {
    model?: Record<string, unknown>;
    game?: Record<string, unknown>;
    runtime?: Record<string, unknown>;
    strategy?: Record<string, unknown>;
    server?: Record<string, unknown>;
    new_api_key?: string | null;
  }) =>
    requestJson<SettingsPayload>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  probeBridge: (baseUrl?: string) =>
    requestJson<BridgeProbeResult>("/api/doctor/bridge", {
      method: "POST",
      body: JSON.stringify(baseUrl ? { base_url: baseUrl } : {}),
    }),

  probeLlm: (payload?: { model?: Record<string, unknown>; new_api_key?: string | null }) =>
    requestJson<LlmProbeResult>("/api/doctor/llm", {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  listRuns: (limit = 100) => requestJson<{ runs: RunSummaryItem[] }>(`/api/runs?limit=${limit}`),

  getRun: (attemptId: string) =>
    requestJson<RunDetailPayload>(`/api/runs/${encodeURIComponent(attemptId)}`),
};
