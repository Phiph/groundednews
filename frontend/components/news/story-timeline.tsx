"use client";
import Link from "next/link";
import { useState } from "react";
import { ExternalLink } from "lucide-react";
import type { ClusterSource, Side } from "@/lib/api";
import { SIDES, SIDE_BG, SIDE_LABELS, SIDE_TEXT, sideOf } from "@/lib/bias";
import { formatClock, formatGap, parseDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const COLLAPSED_COUNT = 6;

type Item = ClusterSource & { side: Side | null; at: number };

/**
 * How coverage spread: when each side first picked the story up, then every
 * article in the order it was published.
 */
export function StoryTimeline({ sources }: { sources: ClusterSource[] }) {
  const [expanded, setExpanded] = useState(false);
  const items: Item[] = sources
    .filter((a) => a.published_at)
    .map((a) => ({ ...a, side: sideOf(a.bias_label), at: parseDate(a.published_at!).getTime() }))
    .sort((a, b) => a.at - b.at);
  if (items.length < 2) return null;

  const start = items[0].at;
  const firstBySide = SIDES.map((side) => ({ side, first: items.find((i) => i.side === side) }));
  const shown = expanded ? items : items.slice(0, COLLAPSED_COUNT);

  return (
    <Card>
      <CardContent className="space-y-5">
        <div className="space-y-1">
          <h2 className="font-heading font-semibold">Timeline</h2>
          <p className="text-sm text-muted-foreground">
            First reported by <span className="font-medium text-foreground">{items[0].source_name}</span> at{" "}
            {formatClock(items[0].published_at!)}.
          </p>
        </div>

        {/* When each side joined in */}
        <div className="grid grid-cols-3 gap-2 text-center">
          {firstBySide.map(({ side, first }) => (
            <div key={side} className="rounded-lg bg-muted/50 px-2 py-2.5">
              <div className={cn("text-xs font-semibold tracking-wide uppercase", SIDE_TEXT[side])}>
                {SIDE_LABELS[side]}
              </div>
              {first ? (
                <>
                  <div className="font-heading text-lg font-bold tabular-nums">
                    {first.at === start ? "First" : formatGap(first.at - start)}
                  </div>
                  <div className="truncate text-xs text-muted-foreground" title={first.source_name}>
                    {first.source_name}
                  </div>
                </>
              ) : (
                <div className="py-1 text-sm text-muted-foreground italic">Not yet</div>
              )}
            </div>
          ))}
        </div>

        {/* Every article, oldest first, on a rail coloured by side */}
        <ol className="relative space-y-4 border-l pl-5">
          {shown.map((a) => (
            <li key={a.url} className="relative">
              <span
                aria-hidden
                className={cn(
                  "absolute top-1 -left-[25px] size-2.5 rounded-full ring-4 ring-card",
                  a.side ? SIDE_BG[a.side] : "bg-muted-foreground"
                )}
              />
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                <time dateTime={new Date(a.at).toISOString()} className="font-medium text-foreground tabular-nums">
                  {formatClock(a.published_at!)}
                </time>
                {a.at > start && <span className="tabular-nums">{formatGap(a.at - start)}</span>}
                <span aria-hidden>·</span>
                <Link href={`/source/${a.source_id}`} className="font-semibold text-foreground hover:underline">
                  {a.source_name}
                </Link>
                <span className="sr-only">({a.side ? SIDE_LABELS[a.side] : "Unrated"})</span>
                {a.is_opinion && <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">Opinion</Badge>}
              </div>
              <a
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group text-sm leading-snug hover:underline"
              >
                {a.title}
                <ExternalLink className="ml-1 inline size-3 opacity-50 group-hover:opacity-100" aria-label="(opens in new tab)" />
              </a>
            </li>
          ))}
        </ol>
        {items.length > COLLAPSED_COUNT && (
          <Button variant="ghost" size="sm" className="w-full" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Show less" : `Show all ${items.length} articles`}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
