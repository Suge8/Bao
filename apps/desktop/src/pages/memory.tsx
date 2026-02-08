import { useI18n } from "@/i18n/i18n";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import { MagicCard } from "@/components/ui/magic-card";
import { ShinyButton } from "@/components/ui/shiny-button";
import { Brain, ChevronDown, Clock, Database, History, RefreshCw, Search } from "lucide-react";
import { cn } from "@/lib/utils";

type MemoryHit = {
  id: string;
  title: string;
  snippet: string;
  score: number;
  namespace?: string;
  kind?: string;
  tags?: string[];
};

type MemoryItem = {
  id: string;
  namespace: string;
  kind: string;
  title: string;
  content?: string | null;
  json?: unknown;
  status?: string;
  score?: number;
  sourceHash?: string;
  createdAt?: number;
  updatedAt?: number;
};

type TimelineItem = {
  namespace: string;
  count: number;
  updatedAt?: number | null;
};

type MemoryVersion = {
  versionId: string;
  memoryId: string;
  prevVersionId?: string | null;
  op: string;
  diffJson?: string;
  actor?: string;
  createdAt?: number;
};

export default function MemoryPage() {
  const { t } = useI18n();
  const client = useClient();

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<MemoryHit[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [itemsById, setItemsById] = useState<Record<string, MemoryItem>>({});
  const [loadingIds, setLoadingIds] = useState<Record<string, boolean>>({});
  const [versionsByMemoryId, setVersionsByMemoryId] = useState<Record<string, MemoryVersion[]>>({});
  const [loadingVersionIds, setLoadingVersionIds] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [rollingVersionKey, setRollingVersionKey] = useState<string | null>(null);

  const refreshTimeline = useCallback(async () => {
    try {
      const res = await client.getTimeline(undefined);
      setTimeline((res.timeline as TimelineItem[]) ?? []);
    } catch {
      setTimeline([]);
    }
  }, [client]);

  useEffect(() => {
    let mounted = true;
    client
      .searchIndex(query, 20)
      .then((res) => {
        if (!mounted) return;
        setHits((res.hits as MemoryHit[]) ?? []);
      })
      .catch((err) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "检索失败");
      });
    return () => {
      mounted = false;
    };
  }, [client, query]);

  useEffect(() => {
    void refreshTimeline();
  }, [refreshTimeline]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return hits;
    return hits.filter((h) => {
      const namespace = h.namespace ?? "";
      const kind = h.kind ?? "";
      return (
        h.title.toLowerCase().includes(q) ||
        h.snippet.toLowerCase().includes(q) ||
        namespace.toLowerCase().includes(q) ||
        kind.toLowerCase().includes(q)
      );
    });
  }, [hits, query]);

  const toggleExpand = async (id: string) => {
    const nextOpen = !expanded[id];
    setExpanded((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      return next;
    });

    if (!nextOpen) return;

    const needItem = !itemsById[id];
    const needVersions = !versionsByMemoryId[id];
    if ((!needItem && !needVersions) || loadingIds[id] || loadingVersionIds[id]) return;

    if (needItem) {
      setLoadingIds((prev) => ({ ...prev, [id]: true }));
    }
    if (needVersions) {
      setLoadingVersionIds((prev) => ({ ...prev, [id]: true }));
    }

    try {
      const [itemResult, versionsResult] = await Promise.all([
        needItem ? client.getItems([id]) : Promise.resolve(null),
        needVersions ? client.listMemoryVersions(id) : Promise.resolve(null),
      ]);

      if (itemResult) {
        const item = (itemResult.items as MemoryItem[])[0];
        if (item) {
          setItemsById((prev) => ({ ...prev, [id]: item }));
        }
      }

      if (versionsResult) {
        const versions = (versionsResult.versions as unknown[])
          .map(normalizeVersion)
          .filter((v): v is MemoryVersion => Boolean(v));
        setVersionsByMemoryId((prev) => ({ ...prev, [id]: versions }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载详情失败");
    } finally {
      if (needItem) {
        setLoadingIds((prev) => ({ ...prev, [id]: false }));
      }
      if (needVersions) {
        setLoadingVersionIds((prev) => ({ ...prev, [id]: false }));
      }
    }
  };

  const rollbackToVersion = async (memoryId: string, versionId: string) => {
    if (!memoryId || !versionId) return;
    setSaving(true);
    setRollingVersionKey(`${memoryId}:${versionId}`);
    setError(null);

    try {
      await client.rollbackVersion(memoryId, versionId);

      const [timelineRes, hitRes, itemRes, versionsRes] = await Promise.all([
        client.getTimeline(undefined),
        client.searchIndex(query, 20),
        client.getItems([memoryId]),
        client.listMemoryVersions(memoryId),
      ]);

      setTimeline((timelineRes.timeline as TimelineItem[]) ?? []);
      setHits((hitRes.hits as MemoryHit[]) ?? []);

      const latestItem = (itemRes.items as MemoryItem[])[0];
      setItemsById((prev) => {
        const next = { ...prev };
        if (latestItem) {
          next[memoryId] = latestItem;
        } else {
          delete next[memoryId];
        }
        return next;
      });

      const versions = (versionsRes.versions as unknown[])
        .map(normalizeVersion)
        .filter((v): v is MemoryVersion => Boolean(v));
      setVersionsByMemoryId((prev) => ({ ...prev, [memoryId]: versions }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "回滚失败");
    } finally {
      setSaving(false);
      setRollingVersionKey(null);
    }
  };

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col overflow-hidden" data-testid="page-memory">
      <div className="flex items-center justify-between">
         <h1 className="text-xl font-bold tracking-tight">{t("page.memory.title")}</h1>
         <ShinyButton
            type="button"
            onClick={() => {
              void refreshTimeline();
            }}
            disabled={saving}
            className="h-8 rounded-xl px-4 text-xs font-medium"
            data-testid="memory-refresh"
          >
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
            Refresh
          </ShinyButton>
      </div>

      <div className="mt-6 min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
      <MagicCard className="rounded-3xl border border-border/50 bg-background/60 backdrop-blur-sm">
        <div className="p-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/50" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search memory graph..."
              className="h-11 w-full rounded-xl bg-muted/30 pl-9 pr-4 text-sm outline-none ring-1 ring-border/50 transition-all focus:bg-muted/50 focus:ring-primary/30"
              data-testid="memory-search"
            />
          </div>

          <div className="mt-6">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Database className="h-3.5 w-3.5" />
              Timeline Overview
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {timeline.map((item) => (
                <div key={item.namespace} className="flex flex-col justify-between rounded-xl bg-muted/30 p-3 ring-1 ring-border/50 transition-colors hover:bg-muted/50">
                  <div className="flex items-center justify-between">
                     <div className="font-mono text-xs font-medium text-foreground">{item.namespace}</div>
                        <div className="rounded-full bg-background px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                       {item.count}
                     </div>
                  </div>
                  <div className="mt-2 flex items-center gap-1 text-[10px] text-muted-foreground/70">
                    <Clock className="h-3 w-3" />
                    {formatUnix(item.updatedAt)}
                  </div>
                </div>
              ))}
              {timeline.length === 0 ? <div className="col-span-full py-4 text-center text-xs text-muted-foreground">No timeline data available.</div> : null}
            </div>
          </div>
        </div>
      </MagicCard>

      {error ? <div className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</div> : null}

      <div className="space-y-2">
        {filtered.map((h) => {
          const isOpen = Boolean(expanded[h.id]);
          const detail = itemsById[h.id];
          const loading = Boolean(loadingIds[h.id]);
          const versions = versionsByMemoryId[h.id] ?? [];
          const loadingVersions = Boolean(loadingVersionIds[h.id]);

          return (
            <motion.div 
              layout 
              key={h.id} 
              className={cn(
                "overflow-hidden rounded-2xl border bg-background/60 backdrop-blur-sm transition-all",
                    isOpen ? "border-primary/20 shadow-sm ring-1 ring-primary/10" : "border-border/50 hover:border-border"
              )}
              data-testid={`memory-hit-${h.id}`}
            >
              <button
                type="button"
                onClick={() => {
                  void toggleExpand(h.id);
                }}
                className="flex w-full items-start justify-between gap-4 p-4 text-left transition-colors hover:bg-muted/30"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Brain className="h-4 w-4 text-primary/70" />
                    <div className="truncate text-sm font-semibold text-foreground">{h.title}</div>
                    <div className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{h.score.toFixed(2)}</div>
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-muted-foreground/80">{h.snippet}</div>
                  <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground/60">
                    <span className="font-mono">{h.namespace}</span>
                    <span>/</span>
                    <span className="font-mono">{h.kind}</span>
                  </div>
                </div>
                <div className={cn("mt-1 transition-transform", isOpen && "rotate-180")}>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </div>
              </button>

              {isOpen ? (
                <div className="border-t border-border/50 bg-muted/10 p-4">
                  {loading ? (
                     <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                        Loading details...
                     </div>
                  ) : null}
                  {!loading && detail ? (
                    <div className="space-y-4">
                      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                        <div className="flex items-center gap-1.5 rounded-lg bg-background/50 px-2 py-1.5">
                           <span className="font-medium">ID:</span>
                           <span className="font-mono">{detail.id}</span>
                        </div>
                        <div className="flex items-center gap-1.5 rounded-lg bg-background/50 px-2 py-1.5">
                           <span className="font-medium">Status:</span>
                           <span>{detail.status ?? "-"}</span>
                        </div>
                        <div className="flex items-center gap-1.5 rounded-lg bg-background/50 px-2 py-1.5">
                           <span className="font-medium">Score:</span>
                           <span>{String(detail.score ?? "-")}</span>
                        </div>
                        <div className="flex items-center gap-1.5 rounded-lg bg-background/50 px-2 py-1.5">
                           <span className="font-medium">Updated:</span>
                           <span>{formatUnix(detail.updatedAt)}</span>
                        </div>
                      </div>

                      <div>
                        <div className="mb-1.5 text-xs font-medium text-muted-foreground">Content</div>
                        <div className="rounded-xl border border-border/50 bg-background p-3 text-xs leading-relaxed text-foreground/90">
                          {detail.content ?? <span className="text-muted-foreground italic">(empty content)</span>}
                        </div>
                      </div>

                      {detail.json ? (
                         <div>
                            <div className="mb-1.5 text-xs font-medium text-muted-foreground">Metadata (JSON)</div>
                            <pre className="max-h-40 overflow-auto rounded-xl border border-border/50 bg-muted/20 p-3 font-mono text-[10px] text-foreground/80 scrollbar-thin scrollbar-thumb-muted-foreground/20">
                              {safeJson(detail.json)}
                            </pre>
                         </div>
                      ) : null}

                      <div className="rounded-xl border border-border/50 bg-background/50 p-3">
                        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                          <History className="h-3.5 w-3.5" />
                          Version History
                        </div>
                        {loadingVersions ? <div className="text-[10px] text-muted-foreground">Loading versions...</div> : null}
                        {!loadingVersions && versions.length === 0 ? (
                          <div className="text-[10px] text-muted-foreground">No version history available.</div>
                        ) : null}
                        {!loadingVersions && versions.length > 0 ? (
                          <div className="space-y-1.5">
                            {versions.map((version) => {
                              const rollbackKey = `${detail.id}:${version.versionId}`;
                              const isRolling = saving && rollingVersionKey === rollbackKey;
                              return (
                                <div
                                  key={version.versionId}
                                  className="flex items-center justify-between rounded-lg bg-muted/30 px-2 py-1.5 transition-colors hover:bg-muted/50"
                                >
                                  <div className="min-w-0 pr-3">
                                    <div className="flex items-center gap-2 text-[10px]">
                                      <span className="font-mono font-medium text-foreground">{version.versionId.slice(0, 8)}...</span>
                                      <span className="rounded bg-background px-1 py-0.5 text-[9px] uppercase tracking-wider text-muted-foreground border border-border/50">{version.op}</span>
                                    </div>
                                    <div className="mt-0.5 truncate text-[10px] text-muted-foreground/70">
                                      {formatUnix(version.createdAt)} · {version.actor ?? "system"}
                                    </div>
                                  </div>
                                  <ShinyButton
                                    type="button"
                                    onClick={() => {
                                      void rollbackToVersion(detail.id, version.versionId);
                                    }}
                                    disabled={saving}
                                    className="h-6 rounded-md px-2 text-[10px]"
                                    data-testid={`memory-rollback-${detail.id}-${version.versionId}`}
                                  >
                                    {isRolling ? "Rolling back..." : "Rollback"}
                                  </ShinyButton>
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  {!loading && !detail ? <div className="text-xs text-muted-foreground">Details not found.</div> : null}
                </div>
              ) : null}
            </motion.div>
          );
        })}
      </div>
      </div>
    </div>
  );
}

function formatUnix(ts?: number | null) {
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function normalizeVersion(raw: unknown): MemoryVersion | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }

  const item = raw as Record<string, unknown>;
  const versionId = readString(item, "versionId", "version_id");
  if (!versionId) {
    return null;
  }

  return {
    versionId,
    memoryId: readString(item, "memoryId", "memory_id") ?? "",
    prevVersionId: readString(item, "prevVersionId", "prev_version_id") ?? null,
    op: readString(item, "op") ?? "UNKNOWN",
    diffJson: readString(item, "diffJson", "diff_json") ?? undefined,
    actor: readString(item, "actor") ?? undefined,
    createdAt: readNumber(item, "createdAt", "created_at"),
  };
}

function readString(obj: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "string") {
      return value;
    }
  }
  return undefined;
}

function readNumber(obj: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return undefined;
}
