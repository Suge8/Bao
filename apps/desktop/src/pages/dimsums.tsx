import { useI18n } from "@/i18n/i18n";
import { motion } from "motion/react";

export default function DimsumsPage() {
  const { t } = useI18n();
  const items = [
    { id: "bao.bundled.mcp-bridge", enabled: true, version: "0.1.0" },
    { id: "bao.bundled.autoevolve", enabled: false, version: "0.1.0" },
    { id: "community.example", enabled: true, version: "0.0.1" },
  ] as const;
  return (
    <div className="mx-auto w-full max-w-5xl space-y-4" data-testid="page-dimsums">
      <div className="text-xl font-semibold">{t("page.dimsums.title")}</div>
      <div className="rounded-2xl bg-foreground/5 p-4">
        <motion.div layout className="grid gap-2">
          {items.map((it) => (
            <motion.div
              layout
              key={it.id}
              className="flex items-center justify-between rounded-2xl bg-background p-3"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{it.id}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">v{it.version}</div>
              </div>
              <button
                type="button"
                className="rounded-xl bg-foreground/5 px-3 py-2 text-xs transition hover:bg-foreground/10"
                data-testid={`dimsum-toggle-${it.id}`}
              >
                {it.enabled ? "Disable" : "Enable"}
              </button>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
