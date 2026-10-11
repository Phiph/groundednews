const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "narrow" });

/** Parse an API timestamp. The backend stores naive UTC, so add the missing "Z". */
export function parseDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

/** Local date and time for an API timestamp. */
export function formatDateTime(iso: string): string {
  return parseDate(iso).toLocaleString();
}

/** "5m ago", "3h ago", "2d ago" relative to now. */
export function timeAgo(iso: string): string {
  const minutes = Math.round((Date.now() - parseDate(iso).getTime()) / 60000);
  if (minutes < 60) return rtf.format(-Math.max(minutes, 1), "minute");
  if (minutes < 1440) return rtf.format(-Math.round(minutes / 60), "hour");
  return rtf.format(-Math.round(minutes / 1440), "day");
}

/** Clock time for an API timestamp, with the weekday when it isn't today: "9:14 AM", "Sat 9:14 AM". */
export function formatClock(iso: string): string {
  const d = parseDate(iso);
  const today = d.toDateString() === new Date().toDateString();
  return d.toLocaleTimeString(undefined, {
    weekday: today ? undefined : "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Gap between two moments, compactly: "+25m", "+3h", "+3h 20m", "+2d". */
export function formatGap(ms: number): string {
  const minutes = Math.round(ms / 60000);
  if (minutes < 1) return "same time";
  if (minutes < 60) return `+${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 && hours < 6 ? `+${hours}h ${minutes % 60}m` : `+${hours}h`;
  return `+${Math.round(hours / 24)}d`;
}
