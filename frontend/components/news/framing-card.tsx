import { Sparkles } from "lucide-react";
import type { Framing, Side } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SIDES, SIDE_BORDER, SIDE_LABELS, SIDE_TEXT } from "@/lib/bias";
import { Card, CardContent } from "@/components/ui/card";

// Static class names so Tailwind picks them up; one column per side present
const COLS: Record<number, string> = { 1: "md:grid-cols-1", 2: "md:grid-cols-2", 3: "md:grid-cols-3" };

/** Sides with a note, in left/center/right order. */
function framedSides(framing: Framing): { side: Side; note: string }[] {
  return SIDES.flatMap((side) => {
    const note = framing[side]?.trim();
    return note ? [{ side, note }] : [];
  });
}

function Caption({ className }: { className?: string }) {
  return (
    <p className={cn("flex items-start gap-1.5 text-xs text-muted-foreground", className)}>
      <Sparkles className="mt-px size-3 shrink-0 opacity-70" aria-hidden />
      <span>Written by Claude from the outlets&apos; headlines and summaries.</span>
    </p>
  );
}

/**
 * AI-written note per side on how its outlets framed the story. Renders nothing without notes.
 * `compact` drops the card and stacks the notes, for use inside story lists.
 */
export function FramingCard({ framing, compact = false }: { framing: Framing; compact?: boolean }) {
  const sides = framedSides(framing ?? {});
  if (sides.length === 0) return null;

  if (compact) {
    return (
      <div className="space-y-2">
        <ul className="space-y-1.5">
          {sides.map(({ side, note }) => (
            <li key={side} className={cn("border-l-2 pl-3 text-sm leading-snug", SIDE_BORDER[side])}>
              <span className={cn("mr-1.5 text-xs font-bold tracking-wide uppercase", SIDE_TEXT[side])}>
                {SIDE_LABELS[side]}
              </span>
              <span className="text-muted-foreground">{note}</span>
            </li>
          ))}
        </ul>
        <Caption className="text-[11px]" />
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-4">
        <h2 className="font-heading font-semibold">How each side framed it</h2>
        <div className={cn("grid gap-5", COLS[sides.length])}>
          {sides.map(({ side, note }) => (
            <div key={side} className="space-y-2">
              <div className={cn("border-b-2 pb-1.5", SIDE_BORDER[side])}>
                <span className={cn("text-sm font-bold tracking-wide uppercase", SIDE_TEXT[side])}>
                  {SIDE_LABELS[side]}
                </span>
              </div>
              <p className="text-sm leading-relaxed">{note}</p>
            </div>
          ))}
        </div>
        <Caption />
      </CardContent>
    </Card>
  );
}
