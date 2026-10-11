const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ClusterSource {
  source_id: number;
  source_name: string;
  bias_label: string;
  title: string;
  url: string;
  published_at: string | null;
  summary?: string;
  image_url?: string;
  is_opinion: boolean;
}

export type Side = "left" | "center" | "right";

export interface BiasBreakdown {
  left: number;
  center: number;
  right: number;
  unknown: number;
  /** Side that is largely ignoring the story, if any */
  blindspot: "left" | "right" | null;
}

/** How each side's outlets framed a story; only sides that covered it, and {} until written. */
export type Framing = Partial<Record<Side, string>>;

export interface Cluster {
  id: number;
  headline: string;
  summary: string;
  category: string;
  tags: string[];
  framing: Framing;
  image_url?: string;
  bias: BiasBreakdown;
  /** Only opinion pieces so far, no straight reporting */
  is_opinion: boolean;
  article_count: number;
  source_count: number;
  first_seen: string;
  last_updated: string;
  sources: ClusterSource[];
}

export interface Source {
  id: number;
  name: string;
  feed_url: string;
  home_url: string;
  bias_label: string;
  enabled: boolean;
  last_scraped: string | null;
  /** Items in the feed on the last fetch */
  article_count: number;
  /** Why the last fetch failed; "" if it worked */
  last_error: string;
  /** Consecutive fetches that failed or returned nothing */
  failure_streak: number;
  last_success: string | null;
  /** When the feed last yielded an unseen article */
  last_new_article: string | null;
}

export interface ScrapeRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  articles_fetched: number;
  articles_new: number;
  clusters_created: number;
  clusters_updated: number;
  status: string;
  error: string;
}

export interface TagCount {
  tag: string;
  count: number;
}

export type OpinionFilter = "exclude" | "only";

export interface SourceSummary {
  id: number;
  name: string;
  home_url: string;
  bias_label: string;
  enabled: boolean;
  /** Counts over the summary window */
  articles: number;
  opinion: number;
  stories: number;
  latest_article: string | null;
}

export interface SourceProfile {
  source: Source;
  days: number;
  articles: number;
  opinion: number;
  stories: number;
  /** Stories at least one other outlet also covered */
  shared_stories: number;
  exclusive_stories: number;
  /** Shared stories where this outlet published first */
  first_reports: number;
  categories: { category: string; count: number }[];
  /** Widely covered recent stories this outlet didn't cover */
  missed: Cluster[];
}

export interface Briefing {
  /** The 24h window, ending at the newest story */
  window_start: string | null;
  window_end: string | null;
  /** Top 10 news stories (no opinion-only) with 2+ outlets, best first */
  stories: Cluster[];
  /** Up to 3 per side, from the wider 72h window */
  blindspots: { left: Cluster[]; right: Cluster[] };
  tags: TagCount[];
  totals: { stories: number; articles: number; outlets: number };
}

/** One day of clustering quality, by when stories first appeared (UTC) */
export interface QualityDay {
  date: string;
  stories: number;
  multi_source: number;
  /** multi_source / stories, 0–1 */
  share: number;
}

export interface SearchResults {
  total: number;
  results: Cluster[];
}

export interface Stats {
  total_clusters: number;
  total_articles: number;
  active_sources: number;
  last_run: ScrapeRun | null;
}

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
  getCluster: (id: number) => apiFetch<Cluster>(`/api/clusters/${id}`),
  getSources: () => apiFetch<Source[]>("/api/sources"),
  getSourcesSummary: (days = 7) =>
    apiFetch<{ days: number; sources: SourceSummary[] }>(`/api/sources/summary?days=${days}`),
  getSourceProfile: (id: number, days = 30) => apiFetch<SourceProfile>(`/api/sources/${id}?days=${days}`),
  createSource: (data: Partial<Source>) =>
    apiFetch<Source>("/api/sources", { method: "POST", body: JSON.stringify(data) }),
  updateSource: (id: number, data: Partial<Source>) =>
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
};
