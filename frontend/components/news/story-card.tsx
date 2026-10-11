"use client";
import Link from "next/link";
import { useState } from "react";
import type { Cluster } from "@/lib/api";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";
import { BiasBar } from "./bias-bar";
import { BlindspotBadge } from "./blindspot-badge";
import { OpinionBadge } from "./opinion-badge";
import { TagLink } from "./tag-link";

type Variant = "lead" | "grid" | "row";

/** Outlet-hosted image; referenced by URL, never stored. Hidden if it fails to load. */
function StoryImage({ src, className }: { src?: string; className?: string }) {
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
      className={cn("rounded-lg bg-muted object-cover", className)}
    />
  );
}

function Meta({ story }: { story: Cluster }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      {story.category && <span className="font-semibold tracking-wide text-foreground/80 uppercase">{story.category}</span>}
      <span aria-hidden>·</span>
      <span>{timeAgo(story.last_updated)}</span>
      <span aria-hidden>·</span>
      <span className="tabular-nums">
        {story.source_count} {story.source_count === 1 ? "source" : "sources"}
      </span>
      {story.is_opinion && <OpinionBadge />}
      {story.bias.blindspot && <BlindspotBadge side={story.bias.blindspot} />}
    </div>
  );
}

/**
 * A story in the feed. The headline link is stretched over the whole card;
 * tags and badges sit above it so they stay independently clickable.
 */
export function StoryCard({ story, variant = "row" }: { story: Cluster; variant?: Variant }) {
  const headline = (
    <Link
      href={`/story/${story.id}`}
      className="after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none after:focus-visible:ring-3 after:focus-visible:ring-ring/50"
    >
      {story.headline}
    </Link>
  );
  const tags = story.tags.length > 0 && (
    <div className="flex flex-wrap gap-1.5">
      {story.tags.map((t) => (
        <TagLink key={t} tag={t} />
      ))}
    </div>
  );

  if (variant === "lead") {
    return (
      <article className="group relative grid gap-5 rounded-xl md:grid-cols-[1.2fr_1fr]">
        <StoryImage src={story.image_url} className="aspect-[16/10] w-full" />
        <div className="flex flex-col gap-3">
          <Meta story={story} />
          <h2 className="font-heading text-2xl leading-tight font-bold tracking-tight text-balance group-hover:underline md:text-3xl">
            {headline}
          </h2>
          {story.summary && <p className="text-[15px] leading-relaxed text-muted-foreground">{story.summary}</p>}
          <BiasBar bias={story.bias} size="lg" className="mt-auto" />
          {tags}
        </div>
      </article>
    );
  }

  if (variant === "grid") {
    return (
      <article className="group relative flex flex-col gap-3 rounded-xl">
        <StoryImage src={story.image_url} className="aspect-[16/9] w-full" />
        <Meta story={story} />
        <h3 className="font-heading text-lg leading-snug font-semibold text-balance group-hover:underline">{headline}</h3>
        {story.summary && <p className="line-clamp-2 text-sm text-muted-foreground">{story.summary}</p>}
        <BiasBar bias={story.bias} className="mt-auto" />
        {tags}
      </article>
    );
  }

  return (
    <article className="group relative flex gap-4 rounded-xl py-4">
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <Meta story={story} />
        <h3 className="font-heading text-base leading-snug font-semibold group-hover:underline">{headline}</h3>
        <BiasBar bias={story.bias} className="max-w-xs" />
        {tags}
      </div>
      <StoryImage src={story.image_url} className="aspect-[4/3] w-24 shrink-0 self-start sm:w-32" />
    </article>
  );
}
