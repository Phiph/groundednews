"use client";
import Link from "next/link";
import { useState } from "react";
import { BookOpen, Lock, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { SIDES, SIDE_BG, SIDE_LABELS, sideOf } from "@/lib/bias";
import { clearReadingHistory, useReadingHistory, type ArticleClick, type StoryView } from "@/lib/reading-history";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StoryCard } from "@/components/news/story-card";
import { StoryRowSkeleton } from "@/components/news/story-skeleton";
import { BalanceBar, BalanceLegend, describeBalance, shares, type SideCounts } from "@/components/diet/balance";

const PERIODS = [
  { value: "7", label: "7 days", days: 7 },
  { value: "30", label: "30 days", days: 30 },
  { value: "all", label: "All time", days: null },
] as const;
type Period = (typeof PERIODS)[number]["value"];

/** Below this many rated article clicks, lead with the coverage of stories read instead. */
const MIN_ARTICLES = 5;
const DAY_MS = 86_400_000;

export default function DietPage() {
  const { history, ready, available, loadedAt } = useReadingHistory();
  const [period, setPeriod] = useState<Period>("30");
  const blindspots = useApi("diet-blindspots", () => api.getClusters({ blindspot: "any", sort: "top", limit: 20 }));

  const days = PERIODS.find((p) => p.value === period)!.days;
  const since = days === null ? 0 : loadedAt - days * DAY_MS;
  const stories = history.stories.filter((s) => s.viewedAt >= since);
  const articles = history.articles.filter((a) => a.clickedAt >= since);
  const hasHistory = history.stories.length + history.articles.length > 0;

  // "Haven't read" means ever, not just in the chosen period
  const readIds = new Set(history.stories.map((s) => s.id));
  const unreadBlindspots = (blindspots.data ?? []).filter((c) => !readIds.has(c.id)).slice(0, 6);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="space-y-1">
          <h1 className="font-heading text-3xl font-bold tracking-tight">My news diet</h1>
          <p className="text-muted-foreground">The political balance of the stories and outlets you read here.</p>
        </div>
        {hasHistory && (
          <div className="flex rounded-lg bg-muted p-0.5 text-sm" role="group" aria-label="Time period">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriod(p.value)}
                aria-pressed={period === p.value}
                className={cn(
                  "rounded-md px-3 py-1 font-medium text-muted-foreground transition-colors",
                  period === p.value && "bg-background text-foreground shadow-sm"
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {!ready ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            {Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
          <Skeleton className="h-56 w-full" />
        </div>
      ) : !available ? (
        <Notice>
          This browser isn&apos;t letting the site save anything (for example in a private window, or with site data
          blocked), so reading history can&apos;t be kept here.
        </Notice>
      ) : !hasHistory ? (
        <EmptyState />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-6">
            <Totals stories={stories} articles={articles} />
            {stories.length + articles.length === 0 ? (
              <Notice>Nothing read in this period. Try a longer one.</Notice>
            ) : (
              <Balance stories={stories} articles={articles} />
            )}
          </div>
          <aside className="space-y-6">
            <Outlets articles={articles} />
            <Categories stories={stories} />
          </aside>
        </div>
      )}

      <section aria-labelledby="blindspots" className="space-y-2">
        <div className="space-y-1">
          <h2 id="blindspots" className="font-heading text-xl font-bold tracking-tight">Blindspots you haven&apos;t read</h2>
          <p className="text-sm text-muted-foreground">
            Top stories that outlets on one side are largely ignoring, minus the ones you&apos;ve opened.
          </p>
        </div>
        {!blindspots.data && blindspots.loading ? (
          <div className="divide-y">{Array.from({ length: 3 }, (_, i) => <StoryRowSkeleton key={i} />)}</div>
        ) : blindspots.error && !blindspots.data ? (
          <p className="py-6 text-sm text-muted-foreground">Couldn&apos;t load blindspot stories.</p>
        ) : unreadBlindspots.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">
            {(blindspots.data ?? []).length === 0
              ? "No blindspot stories right now."
              : "You've read every current blindspot story."}
          </p>
        ) : (
          <div className="divide-y">{unreadBlindspots.map((c) => <StoryCard key={c.id} story={c} variant="row" />)}</div>
        )}
      </section>

      <Footer hasHistory={ready && hasHistory} />
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="py-2 text-sm text-muted-foreground">{children}</CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
        <BookOpen className="size-8 text-muted-foreground" aria-hidden />
        <h2 className="font-heading text-lg font-semibold">Nothing here yet</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          As you open stories and click through to outlets&apos; articles, this page fills up with the political balance
          of what you read, the outlets and topics you read most, and blindspot stories you&apos;ve skipped. Your history
          stays in this browser and is never sent anywhere.
        </p>
        <Button asChild size="sm">
          <Link href="/">Browse top stories</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function Totals({ stories, articles }: { stories: StoryView[]; articles: ArticleClick[] }) {
  const outlets = new Set(articles.map((a) => a.sourceId)).size;
  const blindspotsRead = stories.filter((s) => s.blindspot).length;
  const tiles = [
    { label: "Stories read", value: stories.length, note: `${blindspotsRead} blindspot${blindspotsRead === 1 ? "" : "s"}` },
    { label: "Articles opened", value: articles.length, note: "at the outlet" },
    { label: "Outlets read", value: outlets, note: "different sources" },
  ];
  return (
    <div className="grid grid-cols-3 gap-2 sm:gap-3">
      {tiles.map((t) => (
        <Card key={t.label} size="sm">
          <CardContent className="space-y-0.5">
            <div className="text-xs font-medium text-muted-foreground uppercase">{t.label}</div>
            <div className="font-heading text-2xl font-bold sm:text-3xl">{t.value}</div>
            <div className="text-xs text-muted-foreground">{t.note}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * The centrepiece. Two measures, labelled as such: the outlets behind the articles
 * the reader actually opened, and the coverage of the stories they read (every
 * outlet's report counted). Articles lead once there are enough of them.
 */
function Balance({ stories, articles }: { stories: StoryView[]; articles: ArticleClick[] }) {
  const articleCounts: SideCounts = { left: 0, center: 0, right: 0 };
  let unrated = 0;
  for (const a of articles) {
    const side = sideOf(a.biasLabel);
    if (side) articleCounts[side] += 1;
    else unrated += 1;
  }
  const storyCounts: SideCounts = { left: 0, center: 0, right: 0 };
  for (const s of stories) for (const side of SIDES) storyCounts[side] += s.bias[side];

  const rated = SIDES.reduce((sum, s) => sum + articleCounts[s], 0);
  const reports = SIDES.reduce((sum, s) => sum + storyCounts[s], 0);
  const leadArticles = rated >= MIN_ARTICLES;
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

  const articleMeasure = rated > 0 && (
    <Measure
      title="Articles you opened"
      detail={`by outlet leaning · ${plural(rated, "article", "articles")}`}
      counts={articleCounts}
      unit="articles"
      lead={leadArticles}
    />
  );
  const storyMeasure = reports > 0 && (
    <Measure
      title="Coverage of the stories you read"
      detail={`all outlets reporting · ${plural(stories.length, "story", "stories")}`}
      counts={storyCounts}
      unit="reports"
      lead={!leadArticles}
    />
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bias balance</CardTitle>
        <p className="text-sm text-muted-foreground">
          Share of left, center and right outlets in what you read. Center-left and center-right outlets count toward
          their side.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {rated === 0 && reports === 0 ? (
          <p className="text-sm text-muted-foreground">None of the outlets in this period have a bias rating yet.</p>
        ) : leadArticles || reports === 0 ? (
          <>
            {articleMeasure}
            <p className="text-base font-medium">{describeBalance(articleCounts, "articles")}</p>
            {storyMeasure}
          </>
        ) : (
          <>
            {storyMeasure}
            <p className="text-base font-medium">{describeBalance(storyCounts, "stories")}</p>
            <p className="text-sm text-muted-foreground">
              {rated === 0
                ? "You haven't opened any outlet articles in this period, "
                : `You've opened ${plural(rated, "rated outlet article", "rated outlet articles")} in this period, `}
              so this shows who covered the stories you read. Open {MIN_ARTICLES} or more and the balance of the articles
              themselves is shown first.
            </p>
            {articleMeasure}
          </>
        )}
        {unrated > 0 && (
          <p className="text-xs text-muted-foreground">
            {plural(unrated, "article", "articles")} from unrated outlets {unrated === 1 ? "isn't" : "aren't"} counted.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Measure({
  title,
  detail,
  counts,
  unit,
  lead,
}: {
  title: string;
  detail: string;
  counts: SideCounts;
  unit: string;
  lead: boolean;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <h3 className={cn("font-semibold", lead ? "text-sm" : "text-xs text-muted-foreground")}>{title}</h3>
        <span className="text-xs text-muted-foreground">{detail}</span>
      </div>
      <BalanceBar counts={counts} unit={unit} size={lead ? "lg" : "sm"} />
      {lead ? (
        <BalanceLegend counts={counts} unit={unit} />
      ) : (
        <SmallLegend counts={counts} unit={unit} />
      )}
    </div>
  );
}

/** One-line legend for the secondary measure. */
function SmallLegend({ counts, unit }: { counts: SideCounts; unit: string }) {
  const pct = shares(counts);
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground tabular-nums">
      {SIDES.map((s) => (
        <li key={s} className="flex items-center gap-1" title={`${counts[s]} ${unit}`}>
          <span aria-hidden className={cn("size-1.5 rounded-full", SIDE_BG[s])} />
          {SIDE_LABELS[s]} {pct[s]}%
        </li>
      ))}
    </ul>
  );
}

/** Ranked bar list: one series, so one neutral colour and direct labels. */
function BarList({
  items,
  unit,
}: {
  items: { key: string | number; label: string; href: string; count: number; note?: React.ReactNode }[];
  unit: [string, string];
}) {
  const max = items[0]?.count ?? 1;
  return (
    <ul className="space-y-2.5">
      {items.map((it) => (
        <li key={it.key} title={`${it.label}: ${it.count} ${it.count === 1 ? unit[0] : unit[1]}`}>
          <Link href={it.href} className="group block space-y-1">
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="truncate group-hover:underline">{it.label}</span>
                {it.note}
              </span>
              <span className="shrink-0 text-muted-foreground tabular-nums">{it.count}</span>
            </div>
            <div className="h-2 rounded-r-[4px] bg-foreground/60" style={{ width: `${(it.count / max) * 100}%` }} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Outlets({ articles }: { articles: ArticleClick[] }) {
  const byOutlet = new Map<number, { name: string; biasLabel: string; count: number }>();
  for (const a of articles) {
    const o = byOutlet.get(a.sourceId) ?? { name: a.sourceName, biasLabel: a.biasLabel, count: 0 };
    o.count += 1;
    byOutlet.set(a.sourceId, o);
  }
  const top = [...byOutlet.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 8);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Most-read outlets</CardTitle>
        <p className="text-xs text-muted-foreground">Articles you opened, by outlet.</p>
      </CardHeader>
      <CardContent>
        {top.length === 0 ? (
          <p className="text-sm text-muted-foreground">No outlet articles opened in this period.</p>
        ) : (
          <BarList
            unit={["article", "articles"]}
            items={top.map(([id, o]) => {
              const side = sideOf(o.biasLabel);
              return {
                key: id,
                label: o.name,
                href: `/source/${id}`,
                count: o.count,
                note: (
                  <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground capitalize">
                    <span aria-hidden className={cn("size-1.5 rounded-full", side ? SIDE_BG[side] : "bg-muted-foreground")} />
                    {o.biasLabel || "unrated"}
                  </span>
                ),
              };
            })}
          />
        )}
      </CardContent>
    </Card>
  );
}

function Categories({ stories }: { stories: StoryView[] }) {
  const counts = new Map<string, number>();
  for (const s of stories) if (s.category) counts.set(s.category, (counts.get(s.category) ?? 0) + 1);
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Topics you read</CardTitle>
        <p className="text-xs text-muted-foreground">Stories you opened, by category.</p>
      </CardHeader>
      <CardContent>
        {top.length === 0 ? (
          <p className="text-sm text-muted-foreground">No stories read in this period.</p>
        ) : (
          <BarList
            unit={["story", "stories"]}
            items={top.map(([category, count]) => ({
              key: category,
              label: category,
              href: `/?category=${encodeURIComponent(category)}`,
              count,
            }))}
          />
        )}
      </CardContent>
    </Card>
  );
}

function Footer({ hasHistory }: { hasHistory: boolean }) {
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Lock className="size-3 shrink-0" aria-hidden />
        History is stored only in this browser; clearing site data removes it.
      </p>
      {hasHistory &&
        (confirming ? (
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirm clearing history">
            <span className="text-sm">Clear all reading history?</span>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                clearReadingHistory();
                setConfirming(false);
              }}
            >
              Clear
            </Button>
          </div>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            <Trash2 /> Clear history
          </Button>
        ))}
    </div>
  );
}
