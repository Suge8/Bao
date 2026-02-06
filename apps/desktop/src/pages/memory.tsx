import { useI18n } from "@/i18n/i18n";
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
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

  const refreshTimeline = async () => {
    try {
      const res = await client.getTimeline(undefined);
      setTimeline((res.timeline as TimelineItem[]) ?? []);
    } catch {
      setTimeline([]);
    }
  };

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
  }, [client]);

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
    <div className="mx-auto w-full max-w-5xl space-y-4" data-testid="page-memory">
      <div className="text-xl font-semibold">{t("page.memory.title")}</div>

      <div className="rounded-2xl bg-foreground/5 p-4">
        <div className="flex items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索记忆"
            className="h-10 flex-1 rounded-xl bg-background px-3 text-sm outline-none"
            data-testid="memory-search"
          />
          <button
            type="button"
            onClick={() => {
              void refreshTimeline();
            }}
            disabled={saving}
            className={cn(
              "h-10 rounded-xl px-4 text-sm transition",
              saving
                ? "cursor-not-allowed bg-foreground/10 text-muted-foreground"
                : "bg-foreground text-background hover:opacity-90",
            )}
            data-testid="memory-refresh"
          >
            刷新
          </button>
        </div>

        <div className="mt-3 rounded-xl bg-background p-3">
          <div className="text-xs text-muted-foreground">Timeline（namespace 聚合）</div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {timeline.map((item) => (
              <div key={item.namespace} className="rounded-xl bg-foreground/5 p-2 text-xs text-muted-foreground">
                <div className="text-foreground">{item.namespace}</div>
                <div>count: {item.count}</div>
                <div>updated: {formatUnix(item.updatedAt)}</div>
              </div>
            ))}
            {timeline.length === 0 ? <div className="text-xs text-muted-foreground">暂无 timeline 数据</div> : null}
          </div>
        </div>

        {error ? <div className="mt-2 text-xs text-red-500">{error}</div> : null}

        <motion.div layout className="mt-3 grid gap-2">
          {filtered.map((h) => {
            const isOpen = Boolean(expanded[h.id]);
            const detail = itemsById[h.id];
            const loading = Boolean(loadingIds[h.id]);
            const versions = versionsByMemoryId[h.id] ?? [];
            const loadingVersions = Boolean(loadingVersionIds[h.id]);

            return (
              <motion.div layout key={h.id} className="rounded-2xl bg-background p-3" data-testid={`memory-hit-${h.id}`}>
                <button
                  type="button"
                  onClick={() => {
                    void toggleExpand(h.id);
                  }}
                  className="flex w-full cursor-pointer items-start justify-between gap-3 text-left"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{h.title}</div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{h.snippet}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {(h.namespace ?? "-") + " / " + (h.kind ?? "-")}
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">{h.score.toFixed(2)}</div>
                </button>

                {isOpen ? (
                  <div className="mt-3 rounded-xl bg-foreground/5 p-3 text-xs text-muted-foreground">
                    {loading ? <div>加载详情中...</div> : null}
                    {!loading && detail ? (
                      <>
                        <div className="text-foreground">ID: {detail.id}</div>
                        <div className="mt-1">status: {detail.status ?? "-"}</div>
                        <div className="mt-1">score: {String(detail.score ?? "-")}</div>
                        <div className="mt-1">updated: {formatUnix(detail.updatedAt)}</div>
                        <div className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-background p-2 text-foreground">
                          {detail.content ?? "(empty content)"}
                        </div>
                        <pre className="mt-2 overflow-auto rounded-lg bg-background p-2 text-[11px] text-foreground">
                          {safeJson(detail.json)}
                        </pre>
                        <div className="mt-2 rounded-lg bg-background p-2">
                          <div className="text-[11px] text-muted-foreground">版本历史</div>
                          {loadingVersions ? <div className="mt-1">加载版本中...</div> : null}
                          {!loadingVersions && versions.length === 0 ? (
                            <div className="mt-1">暂无版本</div>
                          ) : null}
                          {!loadingVersions && versions.length > 0 ? (
                            <div className="mt-2 space-y-1">
                              {versions.map((version) => {
                                const rollbackKey = `${detail.id}:${version.versionId}`;
                                const isRolling = saving && rollingVersionKey === rollbackKey;
                                return (
                                  <div
                                    key={version.versionId}
                                    className="flex items-center justify-between rounded-md bg-foreground/5 px-2 py-1"
                                  >
                                    <div className="min-w-0 pr-2 text-[11px] text-muted-foreground">
                                      <div className="truncate text-foreground">{version.versionId}</div>
                                      <div className="truncate">
                                        {version.op} · {formatUnix(version.createdAt)} · {version.actor ?? "-"}
                                      </div>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        void rollbackToVersion(detail.id, version.versionId);
                                      }}
                                      disabled={saving}
                                      className={cn(
                                        "rounded-lg px-2 py-1 text-[11px] transition",
                                        saving
                                          ? "cursor-not-allowed bg-foreground/10 text-muted-foreground"
                                          : "bg-foreground/10 text-foreground hover:bg-foreground/20",
                                      )}
                                      data-testid={`memory-rollback-${detail.id}-${version.versionId}`}
                                    >
                                      {isRolling ? "回滚中" : "回滚到此版本"}
                                    </button>
                                  </div>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
                      </>
                    ) : null}
                    {!loading && !detail ? <div>未加载到详情。</div> : null}
                  </div>
                ) : null}
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </div>
  );
}

function formatUnix(ts?: number | null) {
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString();
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
