"use client";
import { useMemo, useState, type KeyboardEvent } from "react";
import type { QualityDay } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/** Days with fewer stories than this are too small a sample to read much into */
export const LOW_VOLUME = 10;
const Y_TICKS = [0, 0.5, 1];

interface Slot {
  date: string; // YYYY-MM-DD (UTC)
  stories: number;
  multi: number;
  share: number;
  low: boolean;
}

/** The UTC calendar day `offset` days before today, as YYYY-MM-DD. */
function utcDay(offset: number): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - offset);
  return d.toISOString().slice(0, 10);
}

/** Format a plain YYYY-MM-DD without shifting it into the viewer's timezone. */
function formatDay(ymd: string, opts: Intl.DateTimeFormatOptions): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, { ...opts, timeZone: "UTC" });
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Daily share of stories that two or more outlets covered, as columns. Days with little
 * volume are drawn faintly, and a strip underneath shows each day's story count, so a
 * noisy 0% or 100% from a handful of stories doesn't read like a real swing.
 */
export function QualityChart({ data, days = 30 }: { data: QualityDay[]; days?: number }) {
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  const { slots, total, multi, maxStories, today } = useMemo(() => {
    const byDate = new Map(data.map((d) => [d.date, d]));
    // One slot per day, so days with no stories still take their place on the time axis
    const slots: Slot[] = Array.from({ length: days }, (_, i) => {
      const date = utcDay(days - 1 - i);
      const row = byDate.get(date);
      const stories = row?.stories ?? 0;
      const multi = row?.multi_source ?? 0;
      return { date, stories, multi, share: stories ? multi / stories : 0, low: stories < LOW_VOLUME };
    });
    const total = slots.reduce((n, s) => n + s.stories, 0);
    const multi = slots.reduce((n, s) => n + s.multi, 0);
    const maxStories = Math.max(1, ...slots.map((s) => s.stories));
    return { slots, total, multi, maxStories, today: utcDay(0) };
  }, [data, days]);

  if (total === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg bg-muted/40 px-4 text-center text-sm text-muted-foreground">
        No stories in the last {days} days yet. The chart fills in once clustering has run.
      </div>
    );
  }

  const overall = multi / total;
  const n = slots.length;
  const current = active === null ? null : slots[active];
  // Weekly x ticks, counted back from today
  const ticks = slots.map((_, i) => i).filter((i) => (n - 1 - i) % 7 === 0);

  const describe = (s: Slot) =>
    s.stories === 0
      ? `${formatDay(s.date, { month: "short", day: "numeric" })}: no stories`
      : `${formatDay(s.date, { month: "short", day: "numeric" })}: ${pct(s.share)} multi-source, ${s.multi} of ${s.stories} stories${s.low ? " (low volume)" : ""}`;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
    if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      setActive(e.key === "Home" ? 0 : n - 1);
    } else if (step) {
      e.preventDefault();
      setActive((i) => Math.min(n - 1, Math.max(0, (i ?? n) + step)));
    } else if (e.key === "Escape") {
      setActive(null);
    }
  };

  return (
    <div className="space-y-5">
      {/* Headline */}
      <div>
        <div className="text-5xl font-semibold tracking-tight">{pct(overall)}</div>
        <p className="mt-1 text-sm text-muted-foreground">
          of {total.toLocaleString()} stories in the last {days} days were covered by 2+ outlets
          ({multi.toLocaleString()} stories)
        </p>
      </div>

      {/* Key for the encodings that aren't obvious from the title */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] bg-foreground/75" aria-hidden />
          {LOW_VOLUME}+ stories
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] bg-foreground/20" aria-hidden />
          Fewer than {LOW_VOLUME} (noisy)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 rounded-full bg-[#1baf7a] dark:bg-[#199e70]" aria-hidden />
          {days}-day share
        </span>
      </div>

      <div className="flex">
        {/* Y axis gutter */}
        <div className="relative w-9 shrink-0 text-[10px] text-muted-foreground tabular-nums" aria-hidden>
          <div className="relative h-40">
            {Y_TICKS.map((t) => (
              <span key={t} className="absolute right-2 translate-y-1/2 leading-none" style={{ bottom: `${t * 100}%` }}>
                {pct(t)}
              </span>
            ))}
          </div>
          <div className="mt-3 h-8 pr-2 text-right leading-tight">
            <div>Stories</div>
            <div>max {maxStories}</div>
          </div>
        </div>

        <div className="relative min-w-0 flex-1">
          {/* Tooltip: above the plot, kept inside the card at the edges */}
          {current && active !== null && (
            <div
              className={cn(
                "pointer-events-none absolute bottom-full z-10 mb-2 rounded-md bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap text-popover-foreground shadow-md ring-1 ring-foreground/10",
                active < n * 0.25 ? "translate-x-0" : active > n * 0.75 ? "-translate-x-full" : "-translate-x-1/2"
              )}
              style={{
                left: `${((active < n * 0.25 ? active : active > n * 0.75 ? active + 1 : active + 0.5) / n) * 100}%`,
              }}
            >
              <div className="text-muted-foreground">
                {formatDay(current.date, { weekday: "short", month: "short", day: "numeric" })}
                {current.date === today && " (so far)"}
              </div>
              {current.stories === 0 ? (
                <div className="font-medium">No stories</div>
              ) : (
                <>
                  <div className="text-sm font-semibold tabular-nums">{pct(current.share)} multi-source</div>
                  <div className="tabular-nums">
                    {current.multi} of {current.stories} {current.stories === 1 ? "story" : "stories"}
                  </div>
                  {current.low && <div className="text-muted-foreground">Low volume: treat as noise</div>}
                </>
              )}
            </div>
          )}

          <div
            role="group"
            tabIndex={0}
            aria-label={`Daily multi-source share, last ${days} days. Use the arrow keys to step through days.`}
            onKeyDown={onKeyDown}
            onBlur={() => setActive(null)}
            onPointerLeave={() => setActive(null)}
            className="rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {/* Share plot */}
            <div className="relative h-40">
              {Y_TICKS.map((t) => (
                <div key={t} className="absolute inset-x-0 h-px bg-foreground/10" style={{ bottom: `${t * 100}%` }} />
              ))}
              <div className="absolute inset-0 flex">
                {slots.map((s, i) => (
                  <div
                    key={s.date}
                    onPointerEnter={() => setActive(i)}
                    onPointerDown={() => setActive(i)}
                    className={cn("flex h-full min-w-0 flex-1 items-end justify-center px-px", active === i && "bg-foreground/5")}
                  >
                    {s.stories > 0 && (
                      <div
                        className={cn(
                          "w-full max-w-6 rounded-t-[4px] transition-opacity",
                          s.low ? "bg-foreground/20" : "bg-foreground/75",
                          active === i && (s.low ? "bg-foreground/35" : "bg-foreground")
                        )}
                        // A 0% day keeps a sliver so it reads as "measured, none" rather than "no data"
                        style={{ height: s.share > 0 ? `${s.share * 100}%` : "2px" }}
                      />
                    )}
                  </div>
                ))}
              </div>
              {/* Period share reference line */}
              <div
                className="pointer-events-none absolute inset-x-0 h-0.5 -mb-px bg-[#1baf7a] dark:bg-[#199e70]"
                style={{ bottom: `${overall * 100}%` }}
                aria-hidden
              />
            </div>

            {/* Volume strip: same days, story counts */}
            <div className="mt-3 flex h-8 border-b border-foreground/15">
              {slots.map((s, i) => (
                <div
                  key={s.date}
                  onPointerEnter={() => setActive(i)}
                  onPointerDown={() => setActive(i)}
                  className={cn("flex h-full min-w-0 flex-1 items-end justify-center px-px", active === i && "bg-foreground/5")}
                >
                  {s.stories > 0 && (
                    <div
                      className={cn("w-full max-w-6 rounded-t-[2px]", active === i ? "bg-muted-foreground" : "bg-muted-foreground/45")}
                      style={{ height: `${Math.max((s.stories / maxStories) * 100, 6)}%` }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* X axis: weekly ticks ending today */}
          <div className="relative mt-1.5 h-4 text-[10px] text-muted-foreground tabular-nums" aria-hidden>
            {ticks.map((i) => (
              <span
                key={i}
                className={cn("absolute whitespace-nowrap", i === n - 1 ? "right-0" : "-translate-x-1/2")}
                style={i === n - 1 ? undefined : { left: `${((i + 0.5) / n) * 100}%` }}
              >
                {i === n - 1 ? "Today" : formatDay(slots[i].date, { month: "short", day: "numeric" })}
              </span>
            ))}
          </div>

          <p className="sr-only" aria-live="polite">
            {current ? describe(current) : ""}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <Button variant="ghost" size="xs" onClick={() => setShowTable((v) => !v)} aria-expanded={showTable}>
          {showTable ? "Hide table" : "Show as table"}
        </Button>
        {showTable && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Day (UTC)</TableHead>
                <TableHead className="text-right">Stories</TableHead>
                <TableHead className="text-right">2+ outlets</TableHead>
                <TableHead className="text-right">Share</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...slots].reverse().filter((s) => s.stories > 0).map((s) => (
                <TableRow key={s.date} className={cn(s.low && "text-muted-foreground")}>
                  <TableCell>{formatDay(s.date, { weekday: "short", month: "short", day: "numeric" })}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.stories}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.multi}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(s.share)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
