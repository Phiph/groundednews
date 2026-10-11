"use client";
import Link from "next/link";
import { api, type SourceSummary } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { SIDES, SIDE_BORDER, SIDE_LABELS, SIDE_TEXT, sideOf } from "@/lib/bias";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/error-banner";

export default function SourcesPage() {
  const summary = useApi("sources-summary", () => api.getSourcesSummary(7));
  const sources = summary.data?.sources ?? [];
  const unrated = sources.filter((s) => sideOf(s.bias_label) === null);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="font-heading text-3xl font-bold tracking-tight">Sources</h1>
        <p className="text-muted-foreground">
          The outlets GroundedNews follows, by political leaning. Activity is for the last 7 days.
        </p>
      </div>
      {summary.error && <ErrorBanner>{summary.error}</ErrorBanner>}
      <div className="grid gap-8 md:grid-cols-3">
        {SIDES.map((side) => {
          const items = sources.filter((s) => sideOf(s.bias_label) === side);
          return (
            <section key={side} aria-labelledby={`side-${side}`} className="space-y-3">
              <div className={cn("flex items-center justify-between border-b-2 pb-1.5", SIDE_BORDER[side])}>
                <h2 id={`side-${side}`} className={cn("text-sm font-bold tracking-wide uppercase", SIDE_TEXT[side])}>
                  {SIDE_LABELS[side]}
                </h2>
                <span className="text-xs text-muted-foreground tabular-nums">{items.length}</span>
              </div>
              {!summary.data ? (
                Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-16 w-full" />)
              ) : (
                <ul className="space-y-2">{items.map((s) => <SourceRow key={s.id} s={s} />)}</ul>
              )}
            </section>
          );
        })}
      </div>
      {unrated.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-bold tracking-wide text-muted-foreground uppercase">Unrated</h2>
          <ul className="grid gap-2 md:grid-cols-3">{unrated.map((s) => <SourceRow key={s.id} s={s} />)}</ul>
        </section>
      )}
    </div>
  );
}

function SourceRow({ s }: { s: SourceSummary }) {
  const opinionShare = s.articles ? Math.round((s.opinion / s.articles) * 100) : 0;
  return (
    <li>
      <Link
        href={`/source/${s.id}`}
        className={cn("block rounded-lg border px-3 py-2.5 transition-colors hover:bg-muted/60", !s.enabled && "opacity-60")}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">{s.name}</span>
          <Badge variant="outline" className="h-5 px-1.5 text-[10px] capitalize">{s.bias_label || "unrated"}</Badge>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-2 text-xs text-muted-foreground tabular-nums">
          <span>{s.articles} articles</span>
          <span aria-hidden>·</span>
          <span>{s.stories} stories</span>
          {opinionShare > 0 && (
            <>
              <span aria-hidden>·</span>
              <span>{opinionShare}% opinion</span>
            </>
          )}
          {!s.enabled && <span>· paused</span>}
          {s.enabled && s.latest_article && <span className="ml-auto">{timeAgo(s.latest_article)}</span>}
        </div>
      </Link>
    </li>
  );
}
