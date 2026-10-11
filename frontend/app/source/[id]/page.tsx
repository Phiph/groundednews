"use client";
import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, type SourceProfile } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { SIDE_LABELS, SIDE_TEXT, sideOf } from "@/lib/bias";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StoryCard } from "@/components/news/story-card";
import { StoryRowSkeleton } from "@/components/news/story-skeleton";

const PAGE_SIZE = 20;

export default function SourcePage() {
  const { id } = useParams<{ id: string }>();
  const profile = useApi(`source-${id}`, () => api.getSourceProfile(Number(id)));
  const [count, setCount] = useState(PAGE_SIZE);
  const stories = useApi(`source-stories-${id}-${count}`, () =>
    api.getClusters({ source_id: Number(id), sort: "latest", limit: count })
  );
  const p = profile.data;

  if (profile.error) {
    return <p className="py-16 text-center text-muted-foreground">Source not found. <Link href="/sources" className="underline">All sources</Link></p>;
  }
  const side = p ? sideOf(p.source.bias_label) : null;
  const list = stories.data ?? [];

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <Button asChild variant="ghost" size="sm" className="-ml-2.5 text-muted-foreground">
          <Link href="/sources"><ArrowLeft /> All sources</Link>
        </Button>
        {!p ? (
          <Skeleton className="h-10 w-64" />
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h1 className="font-heading text-3xl font-bold tracking-tight">{p.source.name}</h1>
            <Badge variant="outline" className={cn("font-semibold capitalize", side && SIDE_TEXT[side])}>
              {p.source.bias_label || "Unrated"}
              {side && <span className="sr-only"> (counts toward the {SIDE_LABELS[side].toLowerCase()})</span>}
            </Badge>
            {!p.source.enabled && <Badge variant="secondary">Paused</Badge>}
            {p.source.home_url && (
              <a
                href={p.source.home_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground hover:underline"
              >
                {p.source.home_url.replace(/^https?:\/\//, "")}
                <ExternalLink className="size-3" aria-label="(opens in new tab)" />
              </a>
            )}
          </div>
        )}
      </div>

      {p ? <Stats p={p} /> : <Skeleton className="h-24 w-full" />}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section aria-labelledby="recent" className="min-w-0 space-y-2">
          <h2 id="recent" className="font-heading text-xl font-bold tracking-tight">Recent stories</h2>
          {!stories.data && stories.loading ? (
            <div className="divide-y">{Array.from({ length: 4 }, (_, i) => <StoryRowSkeleton key={i} />)}</div>
          ) : list.length === 0 ? (
            <p className="py-8 text-muted-foreground">No stories from this outlet yet.</p>
          ) : (
            <>
              <div className="divide-y">{list.map((s) => <StoryCard key={s.id} story={s} variant="row" />)}</div>
              {list.length === count && (
                <div className="flex justify-center pt-2">
                  <Button variant="outline" disabled={stories.loading} onClick={() => setCount(count + PAGE_SIZE)}>
                    {stories.loading ? "Loading…" : "Load more"}
                  </Button>
                </div>
              )}
            </>
          )}
        </section>

        <aside className="space-y-6">
          {p && <Topics p={p} />}
          {p && <Missed p={p} />}
        </aside>
      </div>
    </div>
  );
}

function Stats({ p }: { p: SourceProfile }) {
  const pct = (n: number, of: number) => (of ? Math.round((n / of) * 100) : 0);
  const tiles = [
    { label: "Articles", value: p.articles, note: `${pct(p.opinion, p.articles)}% opinion` },
    { label: "Stories", value: p.stories, note: `${p.exclusive_stories} only covered here` },
    { label: "Shared stories", value: p.shared_stories, note: `${pct(p.shared_stories, p.stories)}% also covered elsewhere` },
    { label: "Reported first", value: p.first_reports, note: `on ${pct(p.first_reports, p.shared_stories)}% of shared stories` },
  ];
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t) => (
          <Card key={t.label} size="sm">
            <CardContent className="space-y-0.5">
              <div className="text-xs font-medium text-muted-foreground uppercase">{t.label}</div>
              <div className="font-heading text-3xl font-bold tabular-nums">{t.value}</div>
              <div className="text-xs text-muted-foreground">{t.note}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">Last {p.days} days.</p>
    </div>
  );
}

/** Share of the outlet's stories per category: one series, so one colour and direct labels. */
function Topics({ p }: { p: SourceProfile }) {
  if (p.categories.length === 0) return null;
  const max = p.categories[0].count;
  const total = p.categories.reduce((sum, c) => sum + c.count, 0);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Topics covered</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2.5">
          {p.categories.map((c) => {
            const share = Math.round((c.count / total) * 100);
            return (
              <li key={c.category} title={`${c.category}: ${c.count} stories (${share}%)`}>
                <Link href={`/?category=${c.category}`} className="group block space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="group-hover:underline">{c.category}</span>
                    <span className="text-muted-foreground tabular-nums">{share}%</span>
                  </div>
                  <div className="h-2 rounded-r-[4px] bg-foreground/60" style={{ width: `${(c.count / max) * 100}%` }} />
                </Link>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function Missed({ p }: { p: SourceProfile }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Didn&apos;t cover</CardTitle>
        <p className="text-xs text-muted-foreground">
          Stories at least four other outlets covered in the last three days, with nothing from {p.source.name}.
        </p>
      </CardHeader>
      <CardContent>
        {p.missed.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing major missed recently.</p>
        ) : (
          <ul className="space-y-3">
            {p.missed.map((s) => (
              <li key={s.id}>
                <Link href={`/story/${s.id}`} className="group block">
                  <div className="text-sm leading-snug font-medium group-hover:underline">{s.headline}</div>
                  <div className="text-xs text-muted-foreground tabular-nums">{s.source_count} other outlets</div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
