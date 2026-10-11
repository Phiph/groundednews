import type { Side } from "@/lib/api";

export const SIDES: Side[] = ["left", "center", "right"];

export const SIDE_LABELS: Record<Side, string> = { left: "Left", center: "Center", right: "Right" };

/** Tailwind classes per side, backed by the --bias-* tokens in globals.css */
export const SIDE_BG: Record<Side, string> = {
  left: "bg-bias-left",
  center: "bg-bias-center",
  right: "bg-bias-right",
};
export const SIDE_TEXT: Record<Side, string> = {
  left: "text-bias-left",
  center: "text-muted-foreground",
  right: "text-bias-right",
};
export const SIDE_BORDER: Record<Side, string> = {
  left: "border-bias-left",
  center: "border-bias-center",
  right: "border-bias-right",
};

/** Leaning outlets count toward their side, as on Ground News. */
export function sideOf(biasLabel: string): Side | null {
  if (biasLabel === "left" || biasLabel === "center-left") return "left";
  if (biasLabel === "center") return "center";
  if (biasLabel === "right" || biasLabel === "center-right") return "right";
  return null;
}
