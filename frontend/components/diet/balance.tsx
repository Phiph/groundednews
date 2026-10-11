import type { Side } from "@/lib/api";
import { SIDES, SIDE_BG, SIDE_LABELS } from "@/lib/bias";
import { cn } from "@/lib/utils";

export type SideCounts = Record<Side, number>;

/** Whole-number shares that always add up to 100 (largest remainder). */
export function shares(counts: SideCounts): SideCounts {
  const total = SIDES.reduce((sum, s) => sum + counts[s], 0);
  if (total === 0) return { left: 0, center: 0, right: 0 };
  const exact = SIDES.map((s) => ({ s, v: (counts[s] / total) * 100 }));
  const out = Object.fromEntries(exact.map(({ s, v }) => [s, Math.floor(v)])) as SideCounts;
  let rest = 100 - SIDES.reduce((sum, s) => sum + out[s], 0);
  for (const { s } of [...exact].sort((a, b) => (b.v % 1) - (a.v % 1))) {
    if (rest-- <= 0) break;
    out[s] += 1;
  }
  return out;
}

/**
 * Stacked left/center/right bar in the coverage-bar style, with 2px gaps between
 * segments. `lg` carries in-bar labels where they fit; the legend always has the numbers.
 */
export function BalanceBar({
  counts,
  unit,
  size = "lg",
}: {
  counts: SideCounts;
  /** Plural noun for tooltips, e.g. "articles" */
  unit: string;
  size?: "sm" | "lg";
}) {
  const pct = shares(counts);
  const total = SIDES.reduce((sum, s) => sum + counts[s], 0);
  const summary = SIDES.map((s) => `${SIDE_LABELS[s]} ${pct[s]}%`).join(", ");
  return (
    <div
      role="img"
      aria-label={`${summary} of ${unit}`}
      className={cn(
        "flex w-full gap-0.5 overflow-hidden bg-muted",
        size === "lg" ? "h-8 rounded-md text-xs font-semibold" : "h-2 rounded-full"
      )}
    >
      {SIDES.filter((s) => counts[s] > 0).map((s) => (
        <div
          key={s}
          title={`${SIDE_LABELS[s]}: ${counts[s]} ${unit} (${pct[s]}%)`}
          style={{ width: `${(counts[s] / total) * 100}%` }}
          className={cn(
            "flex items-center justify-center whitespace-nowrap transition-opacity hover:opacity-85",
            SIDE_BG[s],
            s === "center" ? "text-black/70" : "text-white"
          )}
        >
          {/* Only label a segment wide enough to hold it, even at phone width */}
          {size === "lg" && pct[s] >= 18 && `${SIDE_LABELS[s][0]} ${pct[s]}%`}
        </div>
      ))}
    </div>
  );
}

/** The numbers behind a BalanceBar: share and count per side, keyed by a colour dot and a name. */
export function BalanceLegend({ counts, unit }: { counts: SideCounts; unit: string }) {
  const pct = shares(counts);
  return (
    <dl className="grid grid-cols-3 gap-2">
      {SIDES.map((s) => (
        <div key={s} className="min-w-0">
          <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden className={cn("size-2 shrink-0 rounded-full", SIDE_BG[s])} />
            {SIDE_LABELS[s]}
          </dt>
          <dd className="font-heading text-xl font-bold">{pct[s]}%</dd>
          <dd className="truncate text-xs text-muted-foreground tabular-nums">
            {counts[s]} {unit}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const SIDE_NAMES: Record<Side, string> = { left: "left-leaning", center: "center", right: "right-leaning" };
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/**
 * A neutral, plain-language reading of a balance. `measure` says what was counted:
 * the articles the reader opened, or the outlets covering the stories they read.
 */
export function describeBalance(counts: SideCounts, measure: "articles" | "stories"): string {
  const pct = shares(counts);
  const [first, second, third] = [...SIDES].sort((a, b) => pct[b] - pct[a]);
  const [n1, n2] = [SIDE_NAMES[first], SIDE_NAMES[second]];
  const art = measure === "articles";
  let text: string;

  if (pct[first] === 100) {
    text = art
      ? `All of the articles you opened came from ${n1} outlets.`
      : `All of the coverage of the stories you read came from ${n1} outlets.`;
  } else if (pct[first] >= 60) {
    text = art
      ? `You read mostly ${n1} outlets: ${pct[first]}% of the articles you opened.`
      : `The stories you read were covered mostly by ${n1} outlets: ${pct[first]}% of their coverage.`;
  } else if (pct[first] - pct[second] < 10 && pct[third] >= 20) {
    text = art
      ? "Your reading is spread fairly evenly across left, center and right outlets."
      : "The stories you read had coverage spread fairly evenly across left, center and right outlets.";
  } else if (pct[first] - pct[second] < 10) {
    text = art
      ? `Your reading is split between ${n1} (${pct[first]}%) and ${n2} (${pct[second]}%) outlets.`
      : `Coverage of the stories you read is split between ${n1} (${pct[first]}%) and ${n2} (${pct[second]}%) outlets.`;
  } else {
    text = art
      ? `${cap(n1)} outlets make up the largest share of what you opened (${pct[first]}%), followed by ${n2} (${pct[second]}%).`
      : `${cap(n1)} outlets account for the largest share of coverage of the stories you read (${pct[first]}%), followed by ${n2} (${pct[second]}%).`;
  }
  const missing = SIDES.filter((s) => counts[s] === 0);
  if (missing.length === 1) text += ` None of it came from ${SIDE_NAMES[missing[0]]} outlets.`;
  return text;
}
