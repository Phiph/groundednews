import { Skeleton } from "@/components/ui/skeleton";

export function StoryRowSkeleton() {
  return (
    <div className="flex gap-4 py-4">
      <div className="flex-1 space-y-2">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-1.5 w-48" />
      </div>
      <Skeleton className="aspect-[4/3] w-24 sm:w-32" />
    </div>
  );
}

export function FeedSkeleton() {
  return (
    <div className="space-y-8">
      <div className="grid gap-5 md:grid-cols-[1.2fr_1fr]">
        <Skeleton className="aspect-[16/10] w-full" />
        <div className="space-y-3">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-7 w-full" />
        </div>
      </div>
      <div className="grid gap-6 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="space-y-3">
            <Skeleton className="aspect-[16/9] w-full" />
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-1.5 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
