"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, EyeOff, Flame, X } from "lucide-react";
import { api, type Cluster, type OpinionFilter } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { ErrorBanner } from "@/components/error-banner";
import { SegmentedControl } from "@/components/segmented-control";
import { BiasBar } from "@/components/news/bias-bar";
import { StoryCard } from "@/components/news/story-card";
import { FeedSkeleton, StoryRowSkeleton } from "@/components/news/story-skeleton";
import { TagLink } from "@/components/news/tag-link";

const CATEGORIES = ["Politics", "World", "Business", "Tech", "Science", "Health", "Sports", "Entertainment", "Environment"];
const PAGE_SIZE = 30;
const CONTENT_FILTERS: { value: OpinionFilter | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "exclude", label: "News" },
  { value: "only", label: "Opinion" },
];
const VIEWS = [
  { value: "top", label: "Top" },
  { value: "latest", label: "Latest" },
] as const;

export default function HomePage() {
  // useSearchParams needs a Suspense boundary
  return (
    <Suspense fallback={<FeedSkeleton />}>
      <Home />
    </Suspense>
  );
}

function Home() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const category = params.get("category") ?? undefined;
  const tag = params.get("tag") ?? undefined;
  const view = params.get("view") === "latest" ? "latest" : "top";
  const multiSourceOnly = params.get("multi") === "1";
  const opinionParam = params.get("opinion");
  const opinion: OpinionFilter | undefined =
    opinionParam === "exclude" || opinionParam === "only" ? opinionParam : undefined;

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // "Load more" grows the page size; it resets whenever the filters change
  const filterKey = `${view}|${category}|${tag}|${multiSourceOnly}|${opinion}`;
  const [pages, setPages] = useState({ key: filterKey, count: 1 });
  const limit = (pages.key === filterKey ? pages.count : 1) * PAGE_SIZE;

  const stories = useApi(`feed|${filterKey}|${limit}`, () =>
    api.getClusters({ sort: view, category, tag, min_sources: multiSourceOnly ? 2 : 1, opinion, limit })
  );
  const trending = useApi("tags", () => api.getTags());
  const blindspots = useApi("blindspots", () => api.getClusters({ blindspot: "any", sort: "top", limit: 5 }));

  const list = stories.data ?? [];
  const canLoadMore = list.length === limit;
  const filtered = Boolean(category || tag);

  return (
    <div className="space-y-6">
      {/* Category navigation */}
      <ScrollArea className="-mx-4 px-4">
        <nav className="flex w-max gap-1 pb-2 text-sm">
          {[undefined, ...CATEGORIES].map((c) => {
            const active = category === c && !tag;
            return (
              <Link
                key={c ?? "all"}
                href={c ? `/?category=${c}` : "/"}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-full px-3 py-1.5 font-medium whitespace-nowrap text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  active && "bg-foreground text-background hover:bg-foreground hover:text-background"
                )}
              >
                {c ?? "Top Stories"}
              </Link>
            );
          })}
        </nav>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>

      {/* Trending tags (sidebar takes over on large screens) */}
      {trending.data && trending.data.length > 0 && (
        <ScrollArea className="-mx-4 px-4 lg:hidden">
          <div className="flex w-max items-center gap-1.5 pb-2">
            <Flame className="size-4 text-blindspot" aria-hidden />
            {trending.data.slice(0, 12).map((t) => (
              <TagLink key={t.tag} tag={t.tag} active={t.tag === tag} />
            ))}
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
      )}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section aria-label="Stories" className="min-w-0 space-y-6">
          {/* Heading + controls */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h1 className="font-heading text-2xl font-bold tracking-tight">
                {tag ? `# ${tag}` : category ?? (view === "top" ? "Top Stories" : "Latest")}
              </h1>
              {filtered && (
                <Button asChild variant="ghost" size="icon-sm" aria-label="Clear filter">
                  <Link href="/">
                    <X />
                  </Link>
                </Button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <SegmentedControl
                label="Show news or opinion"
                options={CONTENT_FILTERS}
                value={opinion ?? null}
                onChange={(v) => setParam("opinion", v)}
              />
              <SegmentedControl
                label="Sort stories"
                options={VIEWS}
                value={view}
                onChange={(v) => setParam("view", v === "top" ? null : v)}
              />
              <div className="flex items-center gap-2">
                <Switch
                  id="multi-source"
                  checked={multiSourceOnly}
                  onCheckedChange={(on) => setParam("multi", on ? "1" : null)}
                />
                <Label htmlFor="multi-source" className="text-sm font-normal text-muted-foreground">
                  2+ sources
                </Label>
              </div>
            </div>
          </div>

          {stories.error && <ErrorBanner>{stories.error}</ErrorBanner>}

          {!stories.data && stories.loading ? (
            <FeedSkeleton />
          ) : list.length === 0 ? (
            <p className="py-16 text-center text-muted-foreground">No stories match these filters yet.</p>
          ) : (
            <div className={cn("space-y-8 transition-opacity", stories.loading && "opacity-60")}>
              <FeedLayout stories={list} />
              {canLoadMore && (
                <div className="flex justify-center">
                  <Button
                    variant="outline"
                    disabled={stories.loading}
                    onClick={() => setPages({ key: filterKey, count: limit / PAGE_SIZE + 1 })}
                  >
                    {stories.loading ? "Loading…" : "Load more stories"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </section>

        <aside className="space-y-6">
          <BlindspotPanel stories={blindspots.data} loading={blindspots.loading} />
          {trending.data && trending.data.length > 0 && (
            <Card className="hidden lg:flex">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Flame className="size-4 text-blindspot" aria-hidden />
                  Trending
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1.5">
                {trending.data.slice(0, 16).map((t) => (
                  <TagLink key={t.tag} tag={t.tag} count={t.count} active={t.tag === tag} />
                ))}
              </CardContent>
            </Card>
          )}
          <BiasLegend />
        </aside>
      </div>
    </div>
  );
}

/** Lead story, a grid of the next four, then a compact list. */
function FeedLayout({ stories }: { stories: Cluster[] }) {
  const [lead, ...rest] = stories;
  const grid = rest.slice(0, 4);
  const more = rest.slice(4);
  return (
    <>
      <StoryCard story={lead} variant="lead" />
      {grid.length > 0 && (
        <>
          <Separator />
          <div className="grid gap-x-6 gap-y-8 sm:grid-cols-2">
            {grid.map((s) => (
              <StoryCard key={s.id} story={s} variant="grid" />
            ))}
          </div>
        </>
      )}
      {more.length > 0 && (
        <>
          <Separator />
          <div className="divide-y">
            {more.map((s) => (
              <StoryCard key={s.id} story={s} variant="row" />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function BlindspotPanel({ stories, loading }: { stories?: Cluster[]; loading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <EyeOff className="size-4 text-blindspot" aria-hidden />
          Blindspots
        </CardTitle>
        <p className="text-xs text-muted-foreground">Stories covered almost entirely by one side.</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {!stories && loading
          ? Array.from({ length: 3 }, (_, i) => <StoryRowSkeleton key={i} />)
          : stories?.map((s) => (
              <Link key={s.id} href={`/story/${s.id}`} className="group block space-y-1.5">
                <div className="text-[11px] font-semibold tracking-wide text-blindspot uppercase">
                  Ignored by the {s.bias.blindspot}
                </div>
                <div className="text-sm leading-snug font-medium group-hover:underline">{s.headline}</div>
                <BiasBar bias={s.bias} />
              </Link>
            ))}
        <Button asChild variant="ghost" size="sm" className="w-full">
          <Link href="/blindspot">
            See all blindspots <ArrowRight />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function BiasLegend() {
  return (
    <Card size="sm" className="text-xs text-muted-foreground">
      <CardContent className="space-y-2">
        <div className="flex gap-3 font-medium text-foreground">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-bias-left" />Left</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-bias-center" />Center</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-bias-right" />Right</span>
        </div>
        <p>
          Bars show the share of outlets on each side covering a story. Leaning outlets count toward their side.
          Ratings can be edited on the <Link href="/admin" className="underline">admin page</Link>.
        </p>
      </CardContent>
    </Card>
  );
}
