import { cn } from "@/lib/utils";
import type { BiasBreakdown } from "@/lib/api";
import { SIDES, SIDE_BG, SIDE_LABELS } from "@/lib/bias";

/**
 * Ground News-style coverage bar: share of outlets on each side covering the story.
 * `lg` puts L/C/R labels inside the segments; `sm` is a thin bar with a text legend.
 */
export function BiasBar({
  bias,
  size = "sm",
  className,
}: {
  bias: BiasBreakdown;
  size?: "sm" | "lg";
  className?: string;
}) {
  const total = bias.left + bias.center + bias.right;
  if (total === 0) return null;
  const pct = (n: number) => Math.round((n / total) * 100);
  const summary = SIDES.map((s) => `${SIDE_LABELS[s]} ${pct(bias[s])}%`).join(", ");

  if (size === "lg") {
    return (
      <div
        role="img"
        aria-label={`Coverage: ${summary}`}
        className={cn("flex h-7 w-full overflow-hidden rounded-md text-xs font-semibold", className)}
      >
        {SIDES.filter((s) => bias[s] > 0).map((s) => (
          <div
            key={s}
            style={{ width: `${pct(bias[s])}%` }}
            className={cn(
              "flex items-center overflow-hidden px-2 whitespace-nowrap",
              SIDE_BG[s],
              s === "center" ? "justify-center text-black/70" : "text-white",
              s === "right" && "justify-end"
            )}
          >
            {pct(bias[s]) >= 12 && `${SIDE_LABELS[s][0]} ${pct(bias[s])}%`}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={cn("space-y-1", className)}>
      <div role="img" aria-label={`Coverage: ${summary}`} className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
        {SIDES.filter((s) => bias[s] > 0).map((s) => (
          <div key={s} style={{ width: `${pct(bias[s])}%` }} className={SIDE_BG[s]} />
        ))}
      </div>
      <div aria-hidden className="flex gap-3 text-[11px] font-medium text-muted-foreground tabular-nums">
        {SIDES.map((s) => (
          <span key={s} className="flex items-center gap-1">
            <span className={cn("size-1.5 rounded-full", SIDE_BG[s])} />
            {SIDE_LABELS[s][0]} {pct(bias[s])}%
          </span>
        ))}
      </div>
    </div>
  );
}
