"use client";
import { EyeOff } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { SIDE_BORDER, SIDE_TEXT } from "@/lib/bias";
import { StoryCard } from "@/components/news/story-card";
import { StoryRowSkeleton } from "@/components/news/story-skeleton";

export default function BlindspotPage() {
  return (
    <div className="space-y-8">
      <div className="max-w-2xl space-y-2">
        <h1 className="flex items-center gap-2 font-heading text-3xl font-bold tracking-tight">
          <EyeOff className="size-7 text-blindspot" aria-hidden /> Blindspot
        </h1>
        <p className="text-muted-foreground">
          Stories covered almost entirely by one side of the political spectrum, so readers of the other side may
          never see them.
        </p>
      </div>
      <div className="grid gap-10 md:grid-cols-2">
        <BlindspotColumn side="left" />
        <BlindspotColumn side="right" />
      </div>
    </div>
  );
}

function BlindspotColumn({ side }: { side: "left" | "right" }) {
  const stories = useApi(`blindspot-${side}`, () => api.getClusters({ blindspot: side, sort: "top", limit: 30 }));
  const other = side === "left" ? "right" : "left";
  return (
    <section className="space-y-2">
      <div className={cn("border-b-2 pb-2", SIDE_BORDER[side])}>
        <h2 className={cn("font-heading text-lg font-bold", SIDE_TEXT[side])}>Blindspot for the {side}</h2>
        <p className="text-sm text-muted-foreground">Mostly reported by {other}-leaning outlets.</p>
      </div>
      {!stories.data && stories.loading ? (
        Array.from({ length: 4 }, (_, i) => <StoryRowSkeleton key={i} />)
      ) : stories.data?.length ? (
        <div className="divide-y">
          {stories.data.map((s) => <StoryCard key={s.id} story={s} variant="row" />)}
        </div>
      ) : (
        <p className="py-8 text-sm text-muted-foreground">No blindspots for the {side} right now.</p>
      )}
    </section>
  );
}
