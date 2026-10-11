import { EyeOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function BlindspotBadge({ side, className }: { side: "left" | "right"; className?: string }) {
  const other = side === "right" ? "left" : "right";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge className={cn("relative z-10 gap-1 bg-blindspot/15 text-blindspot", className)}>
          <EyeOff />
          Blindspot for the {side}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        Covered almost entirely by {other}-leaning outlets; few or no {side}-leaning outlets reported it.
      </TooltipContent>
    </Tooltip>
  );
}
