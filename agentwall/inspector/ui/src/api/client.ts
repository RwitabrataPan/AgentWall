const BASE = "/api";

export type DecisionType = "allow" | "warn" | "block";

export interface Session {
  id: string;
  user_goal: string;
  created_at: number;
  ended_at: number | null;
  meta: Record<string, unknown>;
  event_count: number;
  max_risk: number | null;
  threat_count: number;
}

export interface Evaluation {
  id: number;
  event_id: number;
  decision: DecisionType;
  risk_score: number;
  reason: string;
  llm_used: boolean;
  timestamp: number;
  alignment_score: number | null;
  detector_hits: string[] | null;
  policy_matched: string | null;
}

export interface ToolEvent {
  id: number;
  session_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  timestamp: number;
  tool_type: string | null;
  action: string | null;
  target: string | null;
  resource_category: string | null;
  evaluation: Evaluation | null;
}

export interface Overview {
  active_sessions: number;
  total_sessions: number;
  total_events: number;
  threat_count: number;
  risk_distribution: { allow: number; warn: number; block: number };
}

export interface Policy {
  id: number;
  name: string;
  config: Record<string, unknown>;
  created_at: number;
  enabled: boolean;
}

export interface Provider {
  provider: string;
  model: string;
  priority: number;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface ProviderTestResult {
  provider: string;
  model: string;
  healthy: boolean;
  latency_ms: number | null;
  error: string | null;
}

async function request<T>(
  path: string,
  opts?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return {} as T;
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown) => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  // Health
  health: () => request<{ status: string; version: string }>("/health"),

  // Overview
  getOverview: () => request<Overview>("/overview"),

  // Sessions
  getSessions: () => request<Session[]>("/sessions"),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  endSession: (id: string) => request<{ ok: boolean }>(`/sessions/${id}/end`, { method: "POST" }),

  // Events
  getEvents: (sessionId: string) =>
    request<ToolEvent[]>(`/sessions/${sessionId}/events`),

  // Policies
  getPolicies: () => request<Policy[]>("/policies"),
  createPolicy: (name: string, config: unknown) =>
    request<Policy>("/policies", { method: "POST", ...json({ name, config }) }),
  updatePolicy: (name: string, config: unknown) =>
    request<Policy>(`/policies/${encodeURIComponent(name)}`, { method: "PUT", ...json({ config }) }),
  enablePolicy: (name: string) =>
    request<{ ok: boolean }>(`/policies/${encodeURIComponent(name)}/enable`, { method: "POST" }),
  disablePolicy: (name: string) =>
    request<{ ok: boolean }>(`/policies/${encodeURIComponent(name)}/disable`, { method: "POST" }),
  deletePolicy: (name: string) =>
    request<{ ok: boolean }>(`/policies/${encodeURIComponent(name)}`, { method: "DELETE" }),

  // Providers
  getProviders: () => request<Provider[]>("/providers"),
  updateProvider: (provider: string, data: { model: string; priority: number; enabled: boolean }) =>
    request<Provider>(`/providers/${encodeURIComponent(provider)}`, { method: "PUT", ...json(data) }),
  updateProviderKey: (provider: string, api_key: string) =>
    request<{ ok: boolean }>(`/providers/${encodeURIComponent(provider)}/key`, { method: "POST", ...json({ api_key }) }),
  testProvider: (provider: string) =>
    request<ProviderTestResult>(`/providers/${encodeURIComponent(provider)}/test`, { method: "POST" }),
  deleteProvider: (provider: string) =>
    request<{ ok: boolean }>(`/providers/${encodeURIComponent(provider)}`, { method: "DELETE" }),

  // Export
  exportUrl: (format: "json" | "csv", sessionId?: string) => {
    const params = new URLSearchParams({ format });
    if (sessionId) params.set("session_id", sessionId);
    return `${BASE}/export?${params}`;
  },
};

// WebSocket helper — calls onRefresh whenever new events land
export function connectEventStream(onRefresh: () => void): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/events`);
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data) as { type: string };
      if (msg.type === "refresh") onRefresh();
    } catch { /* ignore */ }
  };
  return () => ws.close();
}
