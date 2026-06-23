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
export interface Workspace {
  id: string;
  name: string;
  created_at: string;
}
export interface ListRow {
  id: string;
  name: string;
  sort_order: number;
  item_count: number;
}
export interface Item {
  id: string;
  title: string;
  status: string;
  fields: Record<string, unknown>;
  due_at: string | null;
  updated_at: string | null;
}
export interface Contact {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  external_ids: Record<string, string>;
  tags: string[];
  created_at: string;
}
export interface ChatSession {
  id: string;
  channel: string;
  mode: "bot" | "human";
  contact_id: string;
  contact_label: string;
  last_body: string | null;
  last_direction: "in" | "out" | null;
  updated_at: string | null;
}
export interface Message {
  id: string;
  direction: "in" | "out";
  body: string | null;
  created_at: string;
}
export interface SocialAccount {
  id: string;
  platform: string;
  external_account_id: string;
  status: string;
  scopes: string[];
  expires_at: string | null;
  rate_limited_until: string | null;
  updated_at: string | null;
}
export interface Post {
  id: string;
  social_account_id: string;
  status: string;
  scheduled_at: string | null;
  attempts: number;
  platform_post_id: string | null;
  last_error: string | null;
  published_at: string | null;
}
export interface Queue {
  id: string;
  name: string;
  color: string;
  greeting_message: string;
  out_of_hours_message: string;
  created_at: string;
}
export interface Ticket {
  id: string;
  status: "pending" | "open" | "closed";
  channel: string;
  unread_count: number;
  last_message: string | null;
  contact_id: string;
  contact_label: string;
  queue_id: string | null;
  queue_name: string | null;
  assigned_user_id: string | null;
  agent_name: string | null;
  updated_at: string | null;
}
export interface ContactList {
  id: string;
  name: string;
  items: number;
  created_at: string;
}
export interface Campaign {
  id: string;
  name: string;
  status: string;
  interval_seconds: number;
  list_name: string | null;
  total: number;
  sent: number;
  scheduled_at: string | null;
  completed_at: string | null;
  created_at: string;
}
export interface QueueOption {
  id: string;
  parent_id: string | null;
  title: string;
  message: string;
  option: string;
}
export interface QueueIntegration {
  id: string;
  queue_id: string | null;
  type: string;
  name: string;
  url_n8n: string | null;
  active: boolean;
}
export interface Template {
  id: string;
  name: string;
  body: string;
  shortcut: string | null;
}
export interface Caption {
  id: string;
  title: string;
  content: string;
  created_at: string;
}
export interface MediaItem {
  id: string;
  parent_id: string | null;
  is_folder: boolean;
  name: string;
  url: string | null;
  mime: string | null;
  size_bytes: number | null;
}
export interface VoiceAgent {
  id: string;
  name: string;
  provider: string;
  agent_id: string;
  status: string;
  created_at: string;
}
export interface BrandVoice {
  id: string;
  name: string;
  tagline: string | null;
  tone: string[];
  avoid: string[];
  personality: string | null;
  industry: string | null;
  autonomy: string;
  created_at: string;
}
export interface ContentPiece {
  id: string;
  type: string;
  platform: string | null;
  title: string;
  body: string | null;
  status: string;
  brand_voice_id: string | null;
  updated_at: string | null;
}
export interface AuditEvent {
  occurred_at: string;
  event_type: string;
  entity_id: string;
  trace_id: string;
  hops: number;
  event_id: string;
  meta: string;
}
export interface TraceStep {
  occurred_at: string;
  event_type: string;
  entity_id: string;
  hops: number;
  event_id: string;
  meta: string;
}
export interface TicketAudit {
  ticket_id: string;
  action: string;
  detail: string | null;
  contact: string;
  at: string;
}
export interface AIModel {
  id: string;
  provider: string;
  label: string;
  model: string;
  base_url: string | null;
  is_default: boolean;
  status: string;
  last_error: string | null;
  has_key: boolean;
  created_at: string;
}
export interface VideoProject {
  id: string;
  name: string;
  content_piece_id: string | null;
  editor_url: string;
  status: string;
  created_at: string;
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

  // Workspace
  workspaces: (agencyId: string) => req<Workspace[]>("/api/workspaces" + q({ agency_id: agencyId })),
  lists: (workspaceId: string) => req<ListRow[]>("/api/lists" + q({ workspace_id: workspaceId })),
  items: (listId: string) => req<Item[]>("/api/items" + q({ list_id: listId })),
  createItem: (body: { list_id: string; agency_id: string; title: string }) =>
    req<{ id: string }>("/api/items", { method: "POST", body: JSON.stringify(body) }),

  // Messaging / chat
  contacts: (agencyId: string) => req<Contact[]>("/api/contacts" + q({ agency_id: agencyId })),
  sessions: (agencyId: string) => req<ChatSession[]>("/api/chat/sessions" + q({ agency_id: agencyId })),
  messages: (sessionId: string) => req<Message[]>(`/api/chat/sessions/${sessionId}/messages`),
  setMode: (sessionId: string, mode: "bot" | "human") =>
    req<{ id: string; mode: string }>(`/api/chat/sessions/${sessionId}/mode`, {
      method: "PATCH",
      body: JSON.stringify({ mode }),
    }),

  // Social
  socialAccounts: (agencyId: string) =>
    req<SocialAccount[]>("/api/social-accounts" + q({ agency_id: agencyId })),
  connectAccount: (body: {
    agency_id: string;
    platform: string;
    external_account_id: string;
    access_token: string;
  }) => req<{ id: string }>("/api/social-accounts", { method: "POST", body: JSON.stringify(body) }),
  posts: (agencyId: string) => req<Post[]>("/api/posts" + q({ agency_id: agencyId, limit: 100 })),
  schedulePost: (body: {
    agency_id: string;
    social_account_id: string;
    caption: string;
    scheduled_at: string;
  }) => req<{ id: string }>("/api/posts", { method: "POST", body: JSON.stringify(body) }),

  // Atendimento (multi-agent inbox — absorbed from WhatICket)
  queues: (agencyId: string) => req<Queue[]>("/api/queues" + q({ agency_id: agencyId })),
  createQueue: (body: { name: string; greeting_message?: string }) =>
    req<{ id: string }>("/api/queues", { method: "POST", body: JSON.stringify(body) }),
  tickets: (status?: string) =>
    req<Ticket[]>("/api/tickets" + (status ? q({ status_filter: status }) : "")),
  createTicket: (body: {
    contact_id: string;
    queue_id?: string;
    channel?: string;
    last_message?: string;
  }) => req<{ id: string }>("/api/tickets", { method: "POST", body: JSON.stringify(body) }),
  updateTicket: (
    id: string,
    body: { status?: string; queue_id?: string; assigned_user_id?: string; rating?: number }
  ) => req<{ id: string; status: string }>(`/api/tickets/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  // Campanhas (bulk — absorbed from WhatICket/WASender)
  contactLists: (agencyId: string) =>
    req<ContactList[]>("/api/contact-lists" + q({ agency_id: agencyId })),
  createContactList: (name: string) =>
    req<{ id: string }>("/api/contact-lists", { method: "POST", body: JSON.stringify({ name }) }),
  addContactItems: (listId: string, items: Array<{ name: string; number: string; email?: string }>) =>
    req<{ added: number }>(`/api/contact-lists/${listId}/items`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  campaigns: (agencyId: string) => req<Campaign[]>("/api/campaigns" + q({ agency_id: agencyId })),
  createCampaign: (body: {
    name: string;
    contact_list_id: string;
    messages: string[];
    interval_seconds: number;
    schedule_now: boolean;
  }) => req<{ id: string }>("/api/campaigns", { method: "POST", body: JSON.stringify(body) }),
  campaignAction: (id: string, action: "schedule" | "cancel") =>
    req<{ id: string; status: string }>(`/api/campaigns/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ action }),
    }),

  // Studio: chatbot tree + integrations + templates
  queueOptions: (queueId: string) => req<QueueOption[]>(`/api/queues/${queueId}/options`),
  createQueueOption: (
    queueId: string,
    body: { title: string; message?: string; option: string; parent_id?: string }
  ) => req<{ id: string }>(`/api/queues/${queueId}/options`, { method: "POST", body: JSON.stringify(body) }),
  queueIntegrations: (agencyId: string) =>
    req<QueueIntegration[]>("/api/queue-integrations" + q({ agency_id: agencyId })),
  createQueueIntegration: (body: {
    type: string;
    name: string;
    queue_id?: string;
    url_n8n?: string;
    prompt?: string;
  }) => req<{ id: string }>("/api/queue-integrations", { method: "POST", body: JSON.stringify(body) }),
  templates: (agencyId: string) => req<Template[]>("/api/templates" + q({ agency_id: agencyId })),
  createTemplate: (body: { name: string; body: string; shortcut?: string }) =>
    req<{ id: string }>("/api/templates", { method: "POST", body: JSON.stringify(body) }),
  renderTemplate: (id: string, variables: Record<string, string>) =>
    req<{ rendered: string }>(`/api/templates/${id}/render`, {
      method: "POST",
      body: JSON.stringify({ variables }),
    }),

  // Biblioteca: captions + media
  captions: (agencyId: string) => req<Caption[]>("/api/captions" + q({ agency_id: agencyId })),
  createCaption: (body: { title: string; content: string }) =>
    req<{ id: string }>("/api/captions", { method: "POST", body: JSON.stringify(body) }),
  media: (parentId?: string) =>
    req<MediaItem[]>("/api/media" + (parentId ? q({ parent_id: parentId }) : "")),
  createMedia: (body: {
    name: string;
    is_folder: boolean;
    parent_id?: string;
    url?: string;
    mime?: string;
  }) => req<{ id: string }>("/api/media", { method: "POST", body: JSON.stringify(body) }),

  // Voz (ElevenLabs Convai — absorbed from voz-panel)
  voiceAgents: (agencyId: string) => req<VoiceAgent[]>("/api/voice-agents" + q({ agency_id: agencyId })),
  createVoiceAgent: (body: { name: string; agent_id: string; provider?: string }) =>
    req<{ id: string }>("/api/voice-agents", { method: "POST", body: JSON.stringify(body) }),
  deleteVoiceAgent: (id: string) => req<void>(`/api/voice-agents/${id}`, { method: "DELETE" }),

  // Growth / Conteúdo (brand voice + content — absorbed from growthOS)
  brandVoices: (agencyId: string) => req<BrandVoice[]>("/api/brand-voices" + q({ agency_id: agencyId })),
  createBrandVoice: (body: {
    name: string;
    tagline?: string;
    tone?: string[];
    avoid?: string[];
    personality?: string;
    industry?: string;
    autonomy?: string;
  }) => req<{ id: string }>("/api/brand-voices", { method: "POST", body: JSON.stringify(body) }),
  contentPieces: (statusFilter?: string) =>
    req<ContentPiece[]>("/api/content-pieces" + (statusFilter ? q({ status_filter: statusFilter }) : "")),
  createContent: (body: { type: string; title: string; platform?: string; body?: string; brand_voice_id?: string }) =>
    req<{ id: string }>("/api/content-pieces", { method: "POST", body: JSON.stringify(body) }),
  updateContent: (id: string, body: { status?: string; body?: string }) =>
    req<{ id: string; status: string }>(`/api/content-pieces/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  lintContent: (text: string, brandVoiceId?: string) =>
    req<{ ok: boolean; violations: string[]; checked: number }>("/api/content-pieces/lint", {
      method: "POST",
      body: JSON.stringify({ body: text, brand_voice_id: brandVoiceId }),
    }),
  generateContent: (body: { type: string; title: string; prompt: string; platform?: string; brand_voice_id?: string }) =>
    req<{ id: string; status: string }>("/api/content-pieces/generate", { method: "POST", body: JSON.stringify(body) }),

  // Auditoria / Console (kairos pattern)
  auditEvents: (eventType?: string) =>
    req<AuditEvent[]>("/api/audit/events" + q(eventType ? { event_type: eventType, limit: 120 } : { limit: 120 })),
  auditTrace: (traceId: string) => req<TraceStep[]>(`/api/audit/trace/${traceId}`),
  auditTickets: () => req<TicketAudit[]>("/api/audit/tickets" + q({ limit: 120 })),

  // IA — LLM models / API keys
  aiProviders: () => req<{ providers: string[]; suggested: Record<string, string[]> }>("/api/ai-models/providers"),
  aiModels: (agencyId: string) => req<AIModel[]>("/api/ai-models" + q({ agency_id: agencyId })),
  createAiModel: (body: { provider: string; label: string; model: string; api_key: string; base_url?: string; make_default?: boolean }) =>
    req<{ id: string }>("/api/ai-models", { method: "POST", body: JSON.stringify(body) }),
  setDefaultAiModel: (id: string) => req<{ id: string }>(`/api/ai-models/${id}/default`, { method: "PATCH" }),
  deleteAiModel: (id: string) => req<void>(`/api/ai-models/${id}`, { method: "DELETE" }),
  testAiModel: (id: string) => req<{ ok: boolean; detail: string }>(`/api/ai-models/${id}/test`, { method: "POST" }),

  // Vídeo — OpenCut companion editor
  videoProjects: (agencyId: string) => req<VideoProject[]>("/api/video-projects" + q({ agency_id: agencyId })),
  createVideoProject: (body: { name: string; content_piece_id?: string; editor_url?: string }) =>
    req<{ id: string }>("/api/video-projects", { method: "POST", body: JSON.stringify(body) }),
  updateVideoProject: (id: string, status: string) =>
    req<{ id: string; status: string }>(`/api/video-projects/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  deleteVideoProject: (id: string) => req<void>(`/api/video-projects/${id}`, { method: "DELETE" }),
};
