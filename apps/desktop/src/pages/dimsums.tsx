import { useI18n } from "@/i18n/i18n";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { MagicCard } from "@/components/ui/magic-card";
import { ShinyButton } from "@/components/ui/shiny-button";
import { Box, Cpu, Layers, Power } from "lucide-react";
import { cn } from "@/lib/utils";

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

  const refresh = useCallback(async () => {
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
  }, [client]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const displayItems = useMemo(() => items.slice(0, 200), [items]);

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col overflow-hidden" data-testid="page-dimsums">
      <div className="flex items-center justify-between">
        <div className="text-xl font-bold tracking-tight">{t("page.dimsums.title")}</div>
        <div className="text-sm text-muted-foreground">
          {displayItems.length} installed
        </div>
      </div>

      <div className="mt-6 min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
        {loading && displayItems.length === 0 ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : null}

        {error ? (
          <div className="rounded-xl bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
        ) : null}

        <motion.div layout className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {displayItems.map((it) => (
          <MagicCard 
            key={it.dimsumId} 
            className="group relative overflow-hidden rounded-3xl border border-border/50 bg-background/60 backdrop-blur-sm transition-all hover:shadow-sm"
          >
            <div className="flex h-full flex-col p-5">
              <div className="flex items-start justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  {it.channel === "bundled" ? <Box className="h-5 w-5" /> : <Layers className="h-5 w-5" />}
                </div>
                <div className={cn("flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-medium uppercase tracking-wider ring-1 ring-inset", 
                  it.enabled 
                    ? "bg-green-500/10 text-green-600 ring-green-500/20 dark:text-green-400" 
                    : "bg-muted text-muted-foreground ring-border"
                )}>
                  {it.enabled ? "Active" : "Disabled"}
                </div>
              </div>

              <div className="mt-4 min-w-0 flex-1">
                <div className="truncate text-base font-semibold tracking-tight text-foreground">
                  {it.manifest?.name ?? it.dimsumId}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground/80">
                  <code className="rounded bg-muted/50 px-1 py-0.5 font-mono text-[10px]">{it.dimsumId}</code>
                </div>
              </div>

              <div className="mt-6 flex items-center justify-between border-t border-border/50 pt-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Cpu className="h-3.5 w-3.5" />
                  <span>v{it.version}</span>
                  <span className="text-muted-foreground/40">•</span>
                  <span className="capitalize">{it.channel}</span>
                </div>
                
                <ShinyButton
                  type="button"
                  className={cn(
                    "h-8 w-8 rounded-lg p-0 transition-colors",
                    it.enabled 
                      ? "text-muted-foreground hover:bg-destructive/10 hover:text-destructive" 
                      : "text-muted-foreground hover:bg-primary/10 hover:text-primary"
                  )}
                  data-testid={`dimsum-toggle-${it.dimsumId}`}
                  onClick={() => {
                    const action = it.enabled ? client.disableDimsum : client.enableDimsum;
                    void action(it.dimsumId)
                      .then(() => refresh())
                      .catch((err) => setError(err instanceof Error ? err.message : "Action failed"));
                  }}
                >
                  <Power className="h-4 w-4" />
                </ShinyButton>
              </div>
            </div>
          </MagicCard>
        ))}
        </motion.div>

        {!loading && displayItems.length === 0 ? (
          <div className="flex h-40 items-center justify-center rounded-3xl border border-dashed border-border/50 bg-muted/20 text-sm text-muted-foreground">
            No dimsums installed.
          </div>
        ) : null}
      </div>
    </div>
  );
}
