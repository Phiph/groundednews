import Link from "next/link";
import { Hash } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** Link to the feed filtered by an ongoing-story tag. Sits above stretched card links. */
export function TagLink({ tag, count, active, className }: { tag: string; count?: number; active?: boolean; className?: string }) {
  return (
    <Badge asChild variant={active ? "default" : "secondary"} className={cn("relative z-10 h-6 px-2.5", className)}>
      <Link href={active ? "/" : `/?tag=${encodeURIComponent(tag)}`}>
        <Hash className="opacity-60" />
        {tag}
        {count !== undefined && <span className="tabular-nums opacity-60">{count}</span>}
      </Link>
    </Badge>
  );
}
