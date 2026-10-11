"use client";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { AlertTriangle, Plus, RefreshCw, Trash2 } from "lucide-react";
import { api, type Source } from "@/lib/api";
import { feedHealth, type FeedHealth, type HealthLevel } from "@/lib/feed-health";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ErrorBanner } from "@/components/error-banner";
import { QualityChart } from "@/components/admin/quality-chart";

const QUALITY_DAYS = 30;
const BIAS_OPTIONS = ["left", "center-left", "center", "center-right", "right"];
const EMPTY_FORM = { name: "", feed_url: "", home_url: "", bias_label: "center" };
const HEALTH_STYLES: Record<HealthLevel, string> = {
  ok: "text-emerald-600 dark:text-emerald-400",
  warning: "text-blindspot",
  failing: "text-destructive",
  paused: "text-muted-foreground",
};

export default function AdminPage() {
  const stats = useApi("stats", () => api.getStats());
  const sources = useApi("sources", () => api.getSources());
  const runs = useApi("runs", () => api.getRuns());
  const quality = useApi("quality", () => api.getQuality(QUALITY_DAYS));
  // Refetch every cached response after a change: stories and summaries depend on sources too
  const { mutate } = useSWRConfig();
  const refresh = () => mutate(() => true);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [error, setError] = useState("");

  const run = async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  };

  const addSource = async () => {
    setSaving(true);
    await run(async () => {
      await api.createSource(form);
      setForm(EMPTY_FORM);
      setShowAdd(false);
    });
    setSaving(false);
  };

  const deleteSource = (s: Source) => {
    if (confirm(`Delete ${s.name}? Its articles stay in the database.`)) run(() => api.deleteSource(s.id));
  };

  const scrape = async () => {
    setScraping(true);
    await run(async () => {
      await api.triggerScrape();
      while ((await api.getScrapeStatus()).running) await new Promise((r) => setTimeout(r, 3000));
    });
    setScraping(false);
  };

  const problems = (sources.data ?? [])
    .map((s) => ({ source: s, health: feedHealth(s) }))
    .filter(({ health }) => health.level === "warning" || health.level === "failing");

  const statusVariant = (s: string) =>
    s === "success" ? "text-emerald-600 dark:text-emerald-400" : s === "failed" ? "text-destructive" : "text-blindspot";

  return (
    <div className="space-y-8">
      <h1 className="font-heading text-3xl font-bold tracking-tight">Admin</h1>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {/* Overview */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Stories" value={stats.data?.total_clusters} />
        <StatCard label="Articles" value={stats.data?.total_articles} />
        <StatCard label="Active sources" value={stats.data?.active_sources} />
        <Card size="sm">
          <CardContent className="space-y-2">
            <div className="text-xs text-muted-foreground">
              Last fetch:{" "}
              {stats.data?.last_run ? formatDateTime(stats.data.last_run.started_at) : "never"}
            </div>
            <Button onClick={scrape} disabled={scraping} className="w-full">
              <RefreshCw className={cn(scraping && "animate-spin")} />
              {scraping ? "Fetching…" : "Fetch articles now"}
            </Button>
            <p className="text-[11px] leading-snug text-muted-foreground">
              Saves new articles only. They&apos;re grouped into stories on the next scheduled run.
            </p>
          </CardContent>
        </Card>
      </div>

      {problems.length > 0 && (
        <div className="flex gap-3 rounded-lg border border-blindspot/30 bg-blindspot/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-blindspot" />
          <div className="space-y-1">
            <p className="font-medium">
              {problems.length} {problems.length === 1 ? "feed needs" : "feeds need"} attention
            </p>
            <ul className="text-muted-foreground">
              {problems.map(({ source, health }) => (
                <li key={source.id}>
                  <span className="font-medium text-foreground">{source.name}</span> ({health.label.toLowerCase()}):{" "}
                  {health.detail}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Clustering quality */}
      <Card>
        <CardHeader>
          <CardTitle>Clustering quality</CardTitle>
          <CardDescription>
            Share of each day&apos;s stories (UTC) that ended up covered by two or more outlets. Feed and
            clustering changes should push it up.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {quality.data ? (
            <QualityChart data={quality.data} days={QUALITY_DAYS} />
          ) : quality.error ? (
            <p className="text-sm text-destructive">{quality.error}</p>
          ) : (
            <div className="h-72 animate-pulse rounded-lg bg-muted/40" />
          )}
        </CardContent>
      </Card>

      {/* Sources */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle>News sources</CardTitle>
            <CardDescription>Bias ratings drive the coverage bars and blindspots.</CardDescription>
          </div>
          <Button variant="outline" onClick={() => setShowAdd(!showAdd)}>
            <Plus /> Add source
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {showAdd && (
            <div className="grid gap-4 rounded-lg border bg-muted/40 p-4 sm:grid-cols-2">
              <Field label="Name" id="name">
                <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="BBC News" />
              </Field>
              <Field label="RSS feed URL" id="feed">
                <Input id="feed" value={form.feed_url} onChange={(e) => setForm({ ...form, feed_url: e.target.value })} placeholder="https://…" />
              </Field>
              <Field label="Home URL" id="home">
                <Input id="home" value={form.home_url} onChange={(e) => setForm({ ...form, home_url: e.target.value })} placeholder="https://bbc.com" />
              </Field>
              <Field label="Bias rating" id="bias">
                <BiasSelect id="bias" value={form.bias_label} onChange={(v) => setForm({ ...form, bias_label: v })} />
              </Field>
              <div className="flex gap-2 sm:col-span-2">
                <Button onClick={addSource} disabled={saving || !form.name || !form.feed_url}>
                  {saving ? "Saving…" : "Save source"}
                </Button>
                <Button variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
              </div>
            </div>
          )}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Health</TableHead>
                <TableHead>Bias</TableHead>
                <TableHead className="hidden md:table-cell">Last scraped</TableHead>
                <TableHead className="text-right">Feed items</TableHead>
                <TableHead>Active</TableHead>
                <TableHead><span className="sr-only">Delete</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.data?.map((s) => (
                <TableRow key={s.id} className={cn(!s.enabled && "opacity-50")}>
                  <TableCell>
                    <div className="font-medium">{s.name}</div>
                    <div className="max-w-[220px] truncate text-xs text-muted-foreground">{s.feed_url}</div>
                  </TableCell>
                  <TableCell>
                    <HealthBadge health={feedHealth(s)} />
                  </TableCell>
                  <TableCell>
                    <BiasSelect
                      value={s.bias_label}
                      onChange={(v) => run(() => api.updateSource(s.id, { bias_label: v }))}
                      className="h-7 w-[130px]"
                    />
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">
                    {s.last_scraped ? formatDateTime(s.last_scraped) : "Never"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{s.article_count}</TableCell>
                  <TableCell>
                    <Switch
                      checked={s.enabled}
                      aria-label={`${s.enabled ? "Pause" : "Enable"} ${s.name}`}
                      onCheckedChange={(on) => run(() => api.updateSource(s.id, { enabled: on }))}
                    />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon-sm" aria-label={`Delete ${s.name}`} onClick={() => deleteSource(s)}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Run history */}
      <Card>
        <CardHeader>
          <CardTitle>Run history</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Started</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Fetched</TableHead>
                <TableHead className="text-right">New</TableHead>
                <TableHead className="text-right">Stories</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{formatDateTime(r.started_at)}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={statusVariant(r.status)}>{r.status}</Badge>
                    {r.error && (
                      <p className="mt-1 max-w-[280px] truncate text-xs text-destructive" title={r.error}>{r.error}</p>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{r.articles_fetched}</TableCell>
                  <TableCell className="text-right tabular-nums">+{r.articles_new}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {r.clusters_created}
                    {r.clusters_updated > 0 && <span className="text-muted-foreground"> (+{r.clusters_updated} updated)</span>}
                  </TableCell>
                  <TableCell className="hidden text-right text-muted-foreground tabular-nums sm:table-cell">
                    {r.finished_at
                      ? `${Math.round((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000)}s`
                      : "—"}
                  </TableCell>
                </TableRow>
              ))}
              {runs.data?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">No runs yet</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function HealthBadge({ health }: { health: FeedHealth }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className={cn("gap-1.5", HEALTH_STYLES[health.level])}>
          <span className="size-1.5 rounded-full bg-current" aria-hidden />
          {health.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{health.detail}</TooltipContent>
    </Tooltip>
  );
}

function StatCard({ label, value }: { label: string; value?: number }) {
  return (
    <Card size="sm">
      <CardContent>
        <div className="font-heading text-3xl font-bold tabular-nums">{value ?? "–"}</div>
        <div className="text-xs font-medium text-muted-foreground uppercase">{label}</div>
      </CardContent>
    </Card>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function BiasSelect({
  value,
  onChange,
  id,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  id?: string;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} className={cn("w-full capitalize", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {BIAS_OPTIONS.map((b) => (
          <SelectItem key={b} value={b} className="capitalize">{b}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
