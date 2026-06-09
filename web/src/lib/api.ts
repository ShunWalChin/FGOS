// Typed FGOS API client. Same-origin relative paths (Vite proxies /api in dev).

const BASE = import.meta.env.VITE_API_BASE ?? "";
const TOKEN_KEY = "fgos_token";

let token: string | null = localStorage.getItem(TOKEN_KEY);

export function setToken(value: string | null): void {
  token = value;
  if (value) localStorage.setItem(TOKEN_KEY, value);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getToken(): string | null {
  return token;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`HTTP ${status}: ${detail}`);
  }
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- types (mirror the FastAPI responses) ---

export interface User {
  id: string;
  email: string;
  agency_id: string;
  role: string;
  full_name?: string | null;
}
export interface LoginResp {
  access_token: string;
  token_type: string;
  user: User;
}
export interface Summary {
  total_events: number;
  event_types: number;
  deal_value_cents: number;
  posts_published: number;
  msgs_in: number;
  msgs_out: number;
}
export interface Breakdown {
  event_type: string;
  n: number;
}
export interface Pipeline {
  id: string;
  name: string;
}
export interface Stage {
  id: string;
  name: string;
  sort_order: number;
  is_won: boolean;
  is_lost: boolean;
}
export interface Deal {
  id: string;
  pipeline_id: string;
  stage_id: string;
  title: string;
  value_cents: number;
  currency: string;
  version: number;
  updated_at: string | null;
}

const q = (params: Record<string, string | number>): string =>
  "?" +
  Object.entries(params)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");

export const api = {
  login: (email: string, password: string) =>
    req<LoginResp>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  summary: (agencyId: string) => req<Summary>("/api/bi/summary" + q({ agency_id: agencyId })),
  breakdown: (agencyId: string) =>
    req<Breakdown[]>("/api/bi/breakdown" + q({ agency_id: agencyId, limit: 12 })),

  pipelines: (agencyId: string) => req<Pipeline[]>("/api/pipelines" + q({ agency_id: agencyId })),
  stages: (pipelineId: string) => req<Stage[]>("/api/stages" + q({ pipeline_id: pipelineId })),
  deals: (agencyId: string) => req<Deal[]>("/api/deals" + q({ agency_id: agencyId, limit: 200 })),

  moveDeal: (id: string, stageId: string, sortOrder: number, version: number) =>
    req<{ id: string; version: number }>(`/api/deals/${id}/move`, {
      method: "PATCH",
      body: JSON.stringify({ stage_id: stageId, sort_order: sortOrder, version }),
    }),

  createDeal: (body: {
    agency_id: string;
    pipeline_id: string;
    stage_id: string;
    title: string;
    value_cents: number;
  }) => req<{ id: string }>("/api/deals", { method: "POST", body: JSON.stringify(body) }),
};
