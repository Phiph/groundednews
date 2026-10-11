"use client";
import { cn } from "@/lib/utils";

/** A row of mutually exclusive toggle buttons, e.g. Top / Latest. */
export function SegmentedControl<T>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex rounded-lg bg-muted p-0.5 text-sm" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.label}
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cn(
            "rounded-md px-3 py-1 font-medium text-muted-foreground transition-colors",
            value === o.value && "bg-background text-foreground shadow-sm"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
