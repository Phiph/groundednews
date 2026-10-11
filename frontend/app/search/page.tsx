"use client";
import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/error-banner";
import { SegmentedControl } from "@/components/segmented-control";
import { StoryCard } from "@/components/news/story-card";
import { StoryRowSkeleton } from "@/components/news/story-skeleton";
import { TagLink } from "@/components/news/tag-link";

const PAGE_SIZE = 30;
const SORTS = [
  { value: "relevance", label: "Best match" },
  { value: "latest", label: "Newest" },
] as const;

export default function SearchPage() {
  // useSearchParams needs a Suspense boundary
  return (
    <Suspense>
      <SearchView />
    </Suspense>
  );
}

function SearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = params.get("q") ?? "";
  const sort = params.get("sort") === "latest" ? "latest" : "relevance";

  // The box updates instantly; the URL (and so the search) follows after a short pause in typing
  const [draft, setDraft] = useState(q);
  useEffect(() => {
    if (draft.trim() === q) return;
    const t = setTimeout(() => {
      const next = new URLSearchParams(params);
      if (draft.trim()) next.set("q", draft.trim());
      else next.delete("q");
      router.replace(`${pathname}?${next}`, { scroll: false });
    }, 250);
    return () => clearTimeout(t);
  }, [draft, q, params, pathname, router]);

  const setSort = (value: "relevance" | "latest") => {
    const next = new URLSearchParams(params);
    if (value === "relevance") next.delete("sort");
    else next.set("sort", value);
    router.replace(`${pathname}?${next}`, { scroll: false });
  };

  // "Load more" grows the page size; it resets when the query or sort changes
  const searchKey = `${q}|${sort}`;
  const [pages, setPages] = useState({ key: searchKey, count: 1 });
  const limit = (pages.key === searchKey ? pages.count : 1) * PAGE_SIZE;

  const results = useApi(`search|${searchKey}|${limit}`, () =>
    q ? api.search(q, { sort, limit }) : Promise.resolve(null)
  );
  const trending = useApi("tags", () => api.getTags());
  const data = results.data;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="font-heading text-3xl font-bold tracking-tight">Search</h1>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search stories, people, places…"
          aria-label="Search stories"
          className="h-11 pl-9 text-base"
        />
      </div>

      {!q ? (
        trending.data && trending.data.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Or follow an ongoing story:</p>
            <div className="flex flex-wrap gap-1.5">
              {trending.data.slice(0, 16).map((t) => <TagLink key={t.tag} tag={t.tag} count={t.count} />)}
            </div>
          </div>
        )
      ) : (
        <section aria-live="polite" className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {data ? (
                <>
                  <span className="font-medium text-foreground tabular-nums">{data.total}</span>{" "}
                  {data.total === 1 ? "story" : "stories"} matching &ldquo;{q}&rdquo;
                </>
              ) : (
                "Searching…"
              )}
            </p>
            <SegmentedControl label="Sort results" options={SORTS} value={sort} onChange={setSort} />
          </div>

          {results.error && <ErrorBanner>{results.error}</ErrorBanner>}

          {!data && results.loading ? (
            <div className="divide-y">{Array.from({ length: 4 }, (_, i) => <StoryRowSkeleton key={i} />)}</div>
          ) : data && data.total === 0 ? (
            <p className="py-12 text-center text-muted-foreground">No stories found. Try fewer or different words.</p>
          ) : (
            <div className={cn("transition-opacity", results.loading && "opacity-60")}>
              <div className="divide-y">
                {data?.results.map((s) => <StoryCard key={s.id} story={s} variant="row" />)}
              </div>
              {data && data.results.length < data.total && (
                <div className="flex justify-center pt-4">
                  <Button
                    variant="outline"
                    disabled={results.loading}
                    onClick={() => setPages({ key: searchKey, count: limit / PAGE_SIZE + 1 })}
                  >
                    {results.loading ? "Loading…" : "Load more"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
