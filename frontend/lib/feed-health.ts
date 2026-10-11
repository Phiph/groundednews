import type { Source } from "./api";
import { parseDate, timeAgo } from "./format";

export type HealthLevel = "ok" | "warning" | "failing" | "paused";

export interface FeedHealth {
  level: HealthLevel;
  label: string;
  detail: string;
}

/** A feed that keeps returning items but nothing new for this long has probably frozen. */
const STALE_HOURS = 24;

export function feedHealth(s: Source): FeedHealth {
  if (!s.enabled) return { level: "paused", label: "Paused", detail: "Not fetched while paused" };
  if (!s.last_scraped) return { level: "ok", label: "Pending", detail: "Not fetched yet" };
  if (s.failure_streak >= 2) {
    return { level: "failing", label: "Failing", detail: `${s.last_error} (${s.failure_streak} fetches in a row)` };
  }
  if (s.failure_streak === 1) return { level: "warning", label: "Warning", detail: `Last fetch: ${s.last_error}` };
  const hoursSinceNew = s.last_new_article ? (Date.now() - parseDate(s.last_new_article).getTime()) / 3.6e6 : Infinity;
  if (hoursSinceNew > STALE_HOURS) {
    return {
      level: "warning",
      label: "Stale",
      detail: s.last_new_article ? `No new articles since ${timeAgo(s.last_new_article)}` : "Has never produced a new article",
    };
  }
  return { level: "ok", label: "Healthy", detail: `New articles ${timeAgo(s.last_new_article!)}` };
}
