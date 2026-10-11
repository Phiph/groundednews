import { MessageSquareQuote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function OpinionBadge({ className }: { className?: string }) {
  return (
    <Badge variant="secondary" className={cn("gap-1", className)}>
      <MessageSquareQuote />
      Opinion
    </Badge>
  );
}
