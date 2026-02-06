import { useI18n } from "@/i18n/i18n";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import { useEffect, useMemo, useState } from "react";

type DimsumItem = {
  dimsumId: string;
  enabled: boolean;
  channel: string;
  version: string;
  manifest?: { name?: string };
};

export default function DimsumsPage() {
  const { t } = useI18n();
  const client = useClient();
  const [items, setItems] = useState<DimsumItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await client.listDimsums();
      const dimsums = (res.dimsums as DimsumItem[]) ?? [];
      setItems(
        [...dimsums].sort((a, b) => {
          if (a.channel === "bundled" && b.channel !== "bundled") return -1;
          if (a.channel !== "bundled" && b.channel === "bundled") return 1;
          return a.dimsumId.localeCompare(b.dimsumId);
        }),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载点心失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [client]);

  const displayItems = useMemo(() => items.slice(0, 200), [items]);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4" data-testid="page-dimsums">
      <div className="text-xl font-semibold">{t("page.dimsums.title")}</div>
      <div className="rounded-2xl bg-foreground/5 p-4">
        {loading ? <div className="text-sm text-muted-foreground">加载中...</div> : null}
        {error ? <div className="mb-2 text-xs text-red-500">{error}</div> : null}

        <motion.div layout className="grid gap-2">
          {displayItems.map((it) => (
            <motion.div
              layout
              key={it.dimsumId}
              className="flex items-center justify-between rounded-2xl bg-background p-3"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{it.manifest?.name ?? it.dimsumId}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {it.dimsumId} · v{it.version} · {it.channel}
                </div>
              </div>
              <button
                type="button"
                className="rounded-xl bg-foreground/5 px-3 py-2 text-xs transition hover:bg-foreground/10"
                data-testid={`dimsum-toggle-${it.dimsumId}`}
                onClick={() => {
                  const action = it.enabled ? client.disableDimsum : client.enableDimsum;
                  void action(it.dimsumId)
                    .then(() => refresh())
                    .catch((err) => setError(err instanceof Error ? err.message : "操作失败"));
                }}
              >
                {it.enabled ? "Disable" : "Enable"}
              </button>
            </motion.div>
          ))}
          {!loading && displayItems.length === 0 ? (
            <div className="rounded-xl bg-background p-3 text-sm text-muted-foreground">暂无点心</div>
          ) : null}
        </motion.div>
      </div>
    </div>
  );
}
