"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, type ClusterSourceDetail, type Side } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { recordArticleClick, recordStoryView } from "@/lib/reading-history";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";
import { SIDES, SIDE_BORDER, SIDE_LABELS, SIDE_TEXT, sideOf } from "@/lib/bias";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { BiasBar } from "@/components/news/bias-bar";
import { BlindspotBadge } from "@/components/news/blindspot-badge";
import { FramingCard } from "@/components/news/framing-card";
import { OpinionBadge } from "@/components/news/opinion-badge";
import { StoryCard } from "@/components/news/story-card";
import { StoryTimeline } from "@/components/news/story-timeline";
import { TagLink } from "@/components/news/tag-link";
import { WriteupCard } from "@/components/news/writeup-card";

export default function StoryPage() {
  const { id } = useParams<{ id: string }>();
  const story = useApi(`story-${id}`, () => api.getCluster(Number(id)));
  const s = story.data;
  const firstTag = s?.tags[0];
  const related = useApi(`related-${id}-${firstTag}`, () =>
    firstTag ? api.getClusters({ tag: firstTag, sort: "top", limit: 7 }) : Promise.resolve([])
  );
  // Remember the visit for "My news diet" (this browser only), once per story
  useEffect(() => {
    if (s) recordStoryView(s);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s?.id]);

  if (story.error) {
    return <p className="py-16 text-center text-muted-foreground">Story not found. <Link href="/" className="underline">Back to home</Link></p>;
  }
  if (!s) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="aspect-[16/8] w-full" />
      </div>
    );
  }

  // Compare straight reporting side by side; opinion gets its own section, unless that's all there is
  const opinion = s.is_opinion ? [] : s.sources.filter((a) => a.is_opinion);
  const reporting = s.sources.filter((a) => !opinion.includes(a));
  const bySide = SIDES.map((side) => ({ side, items: reporting.filter((a) => sideOf(a.bias_label) === side) }));
  const unrated = reporting.filter((a) => sideOf(a.bias_label) === null);
  const relatedStories = (related.data ?? []).filter((r) => r.id !== s.id).slice(0, 6);

  return (
    <article className="space-y-8">
      <div className="mx-auto max-w-3xl space-y-5">
        <Button asChild variant="ghost" size="sm" className="-ml-2.5 text-muted-foreground">
          <Link href="/"><ArrowLeft /> All stories</Link>
        </Button>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          {s.category && (
            <Link href={`/?category=${s.category}`} className="font-semibold tracking-wide text-foreground/80 uppercase hover:underline">
              {s.category}
            </Link>
          )}
          <span aria-hidden>·</span>
          <span>Updated {timeAgo(s.last_updated)}</span>
          {s.is_opinion && <OpinionBadge />}
          {s.bias.blindspot && <BlindspotBadge side={s.bias.blindspot} />}
        </div>
        <h1 className="font-heading text-3xl leading-tight font-bold tracking-tight text-balance md:text-4xl">{s.headline}</h1>
        {s.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {s.tags.map((t) => <TagLink key={t} tag={t} />)}
          </div>
        )}
        <HeroImage src={s.image_url} />
        {s.summary && <p className="text-lg leading-relaxed text-muted-foreground">{s.summary}</p>}

        <Card>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-heading font-semibold">Coverage breakdown</h2>
              <span className="text-sm text-muted-foreground tabular-nums">
                {s.source_count} {s.source_count === 1 ? "source" : "sources"} · {s.article_count}{" "}
                {s.article_count === 1 ? "article" : "articles"}
              </span>
            </div>
            <BiasBar bias={s.bias} size="lg" />
            <div className="grid grid-cols-3 text-center text-sm">
              {SIDES.map((side) => (
                <div key={side}>
                  <div className={cn("font-heading text-xl font-bold tabular-nums", SIDE_TEXT[side])}>{s.bias[side]}</div>
                  <div className="text-xs text-muted-foreground">{SIDE_LABELS[side]} outlets</div>
                </div>
              ))}
            </div>
            {s.bias.blindspot && (
              <p className="rounded-md bg-blindspot/10 px-3 py-2 text-sm">
                <span className="font-semibold text-blindspot">Blindspot for the {s.bias.blindspot}.</span>{" "}
                Few or no {s.bias.blindspot}-leaning outlets covered this story.
              </p>
            )}
          </CardContent>
        </Card>
        <WriteupCard writeup={s.writeup} />
        <FramingCard framing={s.framing} />
        <StoryTimeline sources={s.sources} />
      </div>

      <section aria-labelledby="compare" className="space-y-4">
        <h2 id="compare" className="font-heading text-xl font-bold tracking-tight">How each side covered it</h2>
        <div className="grid gap-6 md:grid-cols-3">
          {bySide.map(({ side, items }) => (
            <SideColumn key={side} side={side} items={items} />
          ))}
        </div>
        {unrated.length > 0 && <SideColumn side={null} items={unrated} />}
      </section>

      {opinion.length > 0 && (
        <section aria-labelledby="opinion" className="space-y-4">
          <div className="flex items-baseline justify-between gap-2 border-b pb-1.5">
            <h2 id="opinion" className="font-heading text-xl font-bold tracking-tight">Opinion &amp; commentary</h2>
            <span className="text-xs text-muted-foreground tabular-nums">{opinion.length}</span>
          </div>
          <ul className="grid gap-x-6 gap-y-4 md:grid-cols-2">
            {opinion.map((a, i) => <ArticleItem key={i} a={a} />)}
          </ul>
        </section>
      )}

      {relatedStories.length > 0 && (
        <section aria-labelledby="related" className="space-y-2">
          <h2 id="related" className="font-heading text-xl font-bold tracking-tight">More on # {firstTag}</h2>
          <div className="divide-y">
            {relatedStories.map((r) => <StoryCard key={r.id} story={r} variant="row" />)}
          </div>
        </section>
      )}
    </article>
  );
}

function HeroImage({ src }: { src?: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    // Outlet-hosted image, referenced not stored
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="aspect-[16/8] w-full rounded-xl bg-muted object-cover"
    />
  );
}

function SideColumn({ side, items }: { side: Side | null; items: ClusterSourceDetail[] }) {
  return (
    <div className="space-y-3">
      <div className={cn("flex items-center justify-between border-b-2 pb-1.5", side ? SIDE_BORDER[side] : "border-border")}>
        <span className={cn("text-sm font-bold tracking-wide uppercase", side ? SIDE_TEXT[side] : "text-muted-foreground")}>
          {side ? SIDE_LABELS[side] : "Unrated"}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground italic">No {side ? SIDE_LABELS[side].toLowerCase() : ""} reporting found.</p>
      ) : (
        <ul className="space-y-4">
          {items.map((a, i) => <ArticleItem key={i} a={a} />)}
        </ul>
      )}
    </div>
  );
}

function ArticleItem({ a }: { a: ClusterSourceDetail }) {
  const { id } = useParams<{ id: string }>();
  // Left or middle click; auxclick also fires for right-click, which isn't a read
  const record = (e: { button: number }) => e.button <= 1 && recordArticleClick(a, Number(id));
  return (
    <li className="space-y-1">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Link href={`/source/${a.source_id}`} className="font-semibold text-foreground hover:underline">
          {a.source_name}
        </Link>
        <Badge variant="outline" className="h-4 px-1.5 text-[10px] capitalize">{a.bias_label}</Badge>
        {a.is_opinion && <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">Opinion</Badge>}
        {a.published_at && <span>{timeAgo(a.published_at)}</span>}
      </div>
      <a
        href={a.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={record}
        onAuxClick={record}
        className="group inline font-medium leading-snug hover:underline"
      >
        {a.title}
        <ExternalLink className="ml-1 inline size-3 opacity-50 group-hover:opacity-100" aria-label="(opens in new tab)" />
      </a>
      {a.summary && <p className="line-clamp-3 text-sm text-muted-foreground">{a.summary}</p>}
    </li>
  );
}
