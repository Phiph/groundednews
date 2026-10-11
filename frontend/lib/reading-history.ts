"use client";
import { useEffect, useState } from "react";
import type { Cluster, ClusterSource } from "@/lib/api";

/**
 * The reader's own history: stories opened and outlet articles clicked through to.
 * Kept only in this browser's localStorage; nothing is sent to the server.
 * Storage can be missing, full or blocked (private windows, previews), so every
 * access is guarded and the site simply works without history when it fails.
 */

const KEY = "gn-reading-v1";
/** Same-tab change notification; other tabs hear the `storage` event instead. */
const EVENT = "gn-reading-history";
const MAX_STORIES = 300;
const MAX_ARTICLES = 500;

export interface StoryView {
  id: number;
  headline: string;
  category: string;
  /** Outlet counts per side from the cluster's coverage breakdown */
  bias: { left: number; center: number; right: number };
  blindspot: "left" | "right" | null;
  /** Epoch ms of the latest view */
  viewedAt: number;
}

export interface ArticleClick {
  url: string;
  sourceId: number;
  sourceName: string;
  biasLabel: string;
  storyId: number;
  /** Epoch ms of the latest click */
  clickedAt: number;
}

/** Both lists are newest first. */
export interface ReadingHistory {
  stories: StoryView[];
  articles: ArticleClick[];
}

const EMPTY: ReadingHistory = { stories: [], articles: [] };

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Parse what's stored, dropping anything malformed rather than failing outright. */
function parse(raw: string | null): ReadingHistory {
  if (!raw) return EMPTY;
  try {
    const data = JSON.parse(raw) as Partial<ReadingHistory>;
    const stories = (Array.isArray(data.stories) ? data.stories : []).filter(
      (s): s is StoryView => !!s && isNum(s.id) && isNum(s.viewedAt) && !!s.bias && typeof s.headline === "string"
    );
    const articles = (Array.isArray(data.articles) ? data.articles : []).filter(
      (a): a is ArticleClick => !!a && typeof a.url === "string" && isNum(a.sourceId) && isNum(a.clickedAt)
    );
    return { stories, articles };
  } catch {
    return EMPTY;
  }
}

function read(): ReadingHistory {
  try {
    return parse(storage()?.getItem(KEY) ?? null);
  } catch {
    return EMPTY;
  }
}

function write(update: (h: ReadingHistory) => ReadingHistory) {
  try {
    const store = storage();
    if (!store) return;
    const next = update(read());
    store.setItem(
      KEY,
      JSON.stringify({ stories: next.stories.slice(0, MAX_STORIES), articles: next.articles.slice(0, MAX_ARTICLES) })
    );
    window.dispatchEvent(new Event(EVENT));
  } catch {
    // Full or blocked: carry on without recording
  }
}

/** Remember that the reader opened a story; re-viewing just moves it to the front. */
export function recordStoryView(cluster: Pick<Cluster, "id" | "headline" | "category" | "bias">) {
  const view: StoryView = {
    id: cluster.id,
    headline: cluster.headline,
    category: cluster.category,
    bias: { left: cluster.bias.left, center: cluster.bias.center, right: cluster.bias.right },
    blindspot: cluster.bias.blindspot,
    viewedAt: Date.now(),
  };
  write((h) => ({ ...h, stories: [view, ...h.stories.filter((s) => s.id !== view.id)] }));
}

/** Remember an outlet article the reader clicked through to; one entry per URL. */
export function recordArticleClick(
  a: Pick<ClusterSource, "source_id" | "source_name" | "bias_label" | "url">,
  storyId: number
) {
  const click: ArticleClick = {
    url: a.url,
    sourceId: a.source_id,
    sourceName: a.source_name,
    biasLabel: a.bias_label,
    storyId,
    clickedAt: Date.now(),
  };
  write((h) => ({ ...h, articles: [click, ...h.articles.filter((x) => x.url !== click.url)] }));
}

export function clearReadingHistory() {
  try {
    storage()?.removeItem(KEY);
    window.dispatchEvent(new Event(EVENT));
  } catch {
    // Nothing we can do; the page keeps showing what it has
  }
}

/** Whether this browser lets us store anything at all. */
function canStore(): boolean {
  try {
    const store = storage();
    if (!store) return false;
    const probe = `${KEY}-probe`;
    store.setItem(probe, "1");
    store.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

/**
 * Current history, kept live across this tab and others. Starts empty on the server
 * and the first client render (no hydration mismatch); `ready` flips once loaded.
 * `loadedAt` is when it was last read, a stable "now" for period filtering.
 */
export function useReadingHistory() {
  const [state, setState] = useState({ history: EMPTY, ready: false, available: true, loadedAt: 0 });

  useEffect(() => {
    const load = () => setState({ history: read(), ready: true, available: canStore(), loadedAt: Date.now() });
    const onStorage = (e: StorageEvent) => {
      // key is null when another tab clears all site storage
      if (e.key === KEY || e.key === null) load();
    };
    load();
    window.addEventListener(EVENT, load);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVENT, load);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return state;
}
