import type { components } from "./api-schema";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// Response types are generated from the backend's response models (backend/schemas.py,
// backend/models.py). After changing those, run `npm run gen:api` to refresh lib/api-schema.ts.
type Schemas = components["schemas"];

export type ClusterSource = Schemas["ClusterSource"];
/** An article on the story page, which also carries its summary */
export type ClusterSourceDetail = Schemas["ClusterSourceDetail"];
export type BiasBreakdown = Schemas["Bias"];
export type Cluster = Schemas["Cluster"];
export type ClusterDetail = Schemas["ClusterDetail"];
export type Source = Schemas["SourcePublic"];
export type SourceCreate = Schemas["SourceCreate"];
export type SourceUpdate = Schemas["SourceUpdate"];
export type ScrapeRun = Schemas["ScrapeRunPublic"];
export type TagCount = Schemas["TagCount"];
export type SourceSummary = Schemas["SourceSummary"];
export type SourceProfile = Schemas["SourceProfile"];
export type Briefing = Schemas["Briefing"];
export type QualityDay = Schemas["QualityDay"];
export type SearchResults = Schemas["SearchResults"];
export type Stats = Schemas["Stats"];
/** A longer AI-written piece (Markdown): story write-up, day's briefing or thread summary. */
export type Writeup = Schemas["Writeup"];

export type Side = "left" | "center" | "right";
export type OpinionFilter = "exclude" | "only";

/** How each side's outlets framed a story; only sides that covered it, and {} until written. */
export type Framing = Partial<Record<Side, string>>;

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  getClusters: (params?: {
    category?: string;
    tag?: string;
    blindspot?: "left" | "right" | "any";
    sort?: "latest" | "top";
    min_sources?: number;
    opinion?: OpinionFilter;
    source_id?: number;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.opinion) qs.set("opinion", params.opinion);
    if (params?.source_id) qs.set("source_id", String(params.source_id));
    if (params?.category) qs.set("category", params.category);
    if (params?.tag) qs.set("tag", params.tag);
    if (params?.blindspot) qs.set("blindspot", params.blindspot);
    if (params?.sort) qs.set("sort", params.sort);
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.min_sources) qs.set("min_sources", String(params.min_sources));
    if (params?.limit) qs.set("limit", String(params.limit));
    return apiFetch<Cluster[]>(`/api/clusters?${qs}`);
  },
  search: (q: string, params?: { sort?: "relevance" | "latest"; limit?: number }) => {
    const qs = new URLSearchParams({ q });
    if (params?.sort) qs.set("sort", params.sort);
    if (params?.limit) qs.set("limit", String(params.limit));
    return apiFetch<SearchResults>(`/api/search?${qs}`);
  },
  getCluster: (id: number) => apiFetch<ClusterDetail>(`/api/clusters/${id}`),
  getSources: () => apiFetch<Source[]>("/api/sources"),
  getSourcesSummary: (days = 7) =>
    apiFetch<{ days: number; sources: SourceSummary[] }>(`/api/sources/summary?days=${days}`),
  getSourceProfile: (id: number, days = 30) => apiFetch<SourceProfile>(`/api/sources/${id}?days=${days}`),
  createSource: (data: SourceCreate) =>
    apiFetch<Source>("/api/sources", { method: "POST", body: JSON.stringify(data) }),
  updateSource: (id: number, data: SourceUpdate) =>
    apiFetch<Source>(`/api/sources/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteSource: (id: number) =>
    apiFetch<void>(`/api/sources/${id}`, { method: "DELETE" }),
  getRuns: () => apiFetch<ScrapeRun[]>("/api/runs"),
  triggerScrape: () => apiFetch<{ status: string }>("/api/scrape", { method: "POST" }),
  getScrapeStatus: () => apiFetch<{ running: boolean }>("/api/scrape/status"),
  getStats: () => apiFetch<Stats>("/api/stats"),
  getBriefing: () => apiFetch<Briefing>("/api/briefing"),
  getQuality: (days = 14) => apiFetch<QualityDay[]>(`/api/stats/quality?days=${days}`),
  getTags: (days = 7) => apiFetch<TagCount[]>(`/api/tags?days=${days}`),
  /** A thread's "where things stand" summary, or null if none has been written. */
  getThreadWriteup: async (tag: string): Promise<Writeup | null> => {
    try {
      return await apiFetch<Writeup>(`/api/threads/${encodeURIComponent(tag)}`);
    } catch (e) {
      if (e instanceof Error && e.message.startsWith("API error 404")) return null;
      throw e;
    }
  },
};
