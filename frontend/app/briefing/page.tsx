"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { api, type Cluster } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { formatClock, parseDate, timeAgo } from "@/lib/format";
import { SIDE_BORDER, SIDE_TEXT } from "@/lib/bias";
import { Skeleton } from "@/components/ui/skeleton";
import { BiasBar } from "@/components/news/bias-bar";
import { FramingCard } from "@/components/news/framing-card";
import { StoryCard } from "@/components/news/story-card";
import { StoryRowSkeleton } from "@/components/news/story-skeleton";
import { TagLink } from "@/components/news/tag-link";

const plural = (n: number, word: string) => `${n.toLocaleString()} ${n === 1 ? word : `${word}s`}`;

export default function BriefingPage() {
  const briefing = useApi("briefing", () => api.getBriefing());
  const b = briefing.data;

  if (briefing.error && !b) {
    return (
      <div className="mx-auto max-w-3xl rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {briefing.error}
      </div>
    );
  }
  if (!b) return <BriefingSkeleton />;

  const end = b.window_end;
  return (
    <div className="mx-auto max-w-3xl space-y-12">
      <header className="space-y-2 border-b pb-5">
        {end && (
          <p className="text-xs font-semibold tracking-wide text-foreground/80 uppercase">
            {parseDate(end).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </p>
        )}
        <h1 className="font-heading text-3xl font-bold tracking-tight md:text-4xl">Briefing</h1>
        <p className="text-muted-foreground">
          {end ? `Last 24 hours, to ${formatClock(end)}` : "Nothing in the last 24 hours yet"}
          {b.totals.stories > 0 && (
            <>
              {" · "}
              <span className="tabular-nums">
                {plural(b.totals.stories, "story")} from {plural(b.totals.outlets, "outlet")},{" "}
                {plural(b.totals.articles, "article")}
              </span>
            </>
          )}
        </p>
      </header>

      <section aria-labelledby="top-stories" className="space-y-2">
        <h2 id="top-stories" className="font-heading text-xl font-bold tracking-tight">Top stories</h2>
        {b.stories.length === 0 ? (
          <p className="py-8 text-sm text-muted-foreground">No stories with more than one outlet in this window.</p>
        ) : (
          <ol className="divide-y">
            {b.stories.map((s, i) => <BriefingItem key={s.id} story={s} rank={i + 1} />)}
          </ol>
        )}
      </section>

      <section aria-labelledby="blindspots" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="blindspots" className="font-heading text-xl font-bold tracking-tight">Blindspots</h2>
          <Link href="/blindspot" className="flex items-center gap-1 text-sm text-muted-foreground hover:underline">
            All blindspots <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>
        <div className="grid gap-8 md:grid-cols-2">
          <BlindspotGroup side="left" stories={b.blindspots.left} />
          <BlindspotGroup side="right" stories={b.blindspots.right} />
        </div>
      </section>

      {b.tags.length > 0 && (
        <section aria-labelledby="threads" className="space-y-3">
          <h2 id="threads" className="font-heading text-xl font-bold tracking-tight">Threads to follow</h2>
          <div className="flex flex-wrap gap-1.5">
            {b.tags.map((t) => <TagLink key={t.tag} tag={t.tag} count={t.count} />)}
          </div>
        </section>
      )}
    </div>
  );
}

function BriefingItem({ story: s, rank }: { story: Cluster; rank: number }) {
  return (
    <li className="grid grid-cols-[2rem_1fr] gap-x-3 py-6 sm:grid-cols-[2.5rem_1fr] sm:gap-x-4">
      <span aria-hidden className="font-heading text-2xl leading-none font-bold text-muted-foreground/60 tabular-nums sm:text-3xl">
        {rank}
      </span>
      <div className="min-w-0 space-y-3">
        <div className="flex gap-4">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              {s.category && <span className="font-semibold tracking-wide text-foreground/80 uppercase">{s.category}</span>}
              {s.category && <span aria-hidden>·</span>}
              <span className="tabular-nums">{plural(s.source_count, "source")}</span>
              <span aria-hidden>·</span>
              <span>{timeAgo(s.last_updated)}</span>
            </div>
            <h3 className="font-heading text-lg leading-snug font-semibold text-balance">
              <Link href={`/story/${s.id}`} className="hover:underline">{s.headline}</Link>
            </h3>
          </div>
          <BriefingImage src={s.image_url} />
        </div>
        {s.summary && <p className="text-[15px] leading-relaxed text-muted-foreground">{s.summary}</p>}
        <BiasBar bias={s.bias} className="max-w-xs" />
        <FramingCard framing={s.framing} compact />
      </div>
    </li>
  );
}

/** Outlet-hosted thumbnail; referenced by URL, never stored. Hidden on phones and if it fails to load. */
function BriefingImage({ src }: { src?: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="hidden aspect-[4/3] w-28 shrink-0 self-start rounded-lg bg-muted object-cover sm:block"
    />
  );
}

// "left" holds stories the left is ignoring, i.e. covered mostly by the right
function BlindspotGroup({ side, stories }: { side: "left" | "right"; stories: Cluster[] }) {
  const other = side === "left" ? "right" : "left";
  return (
    <div className="space-y-1">
      <div className={cn("border-b-2 pb-2", SIDE_BORDER[side])}>
        <h3 className={cn("font-heading font-bold", SIDE_TEXT[side])}>Ignored by the {side}</h3>
        <p className="text-sm text-muted-foreground">Mostly reported by {other}-leaning outlets.</p>
      </div>
      {stories.length === 0 ? (
        <p className="py-6 text-sm text-muted-foreground">Nothing the {side} is missing right now.</p>
      ) : (
        <div className="divide-y">
          {stories.map((s) => <StoryCard key={s.id} story={s} variant="row" />)}
        </div>
      )}
    </div>
  );
}

function BriefingSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <div className="space-y-3 border-b pb-5">
        <Skeleton className="h-3 w-36" />
        <Skeleton className="h-9 w-40" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <div className="divide-y">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="grid grid-cols-[2rem_1fr] gap-x-3 sm:grid-cols-[2.5rem_1fr] sm:gap-x-4">
            <Skeleton className="mt-4 size-6" />
            <StoryRowSkeleton />
          </div>
        ))}
      </div>
    </div>
  );
}
