import { useI18n } from "@/i18n/i18n";
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";

export default function MemoryPage() {
  const { t } = useI18n();
  const client = useClient();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<
    { id: string; title: string; snippet: string; score: number; tags?: string[] }[]
  >([]);

  useEffect(() => {
    let mounted = true;
    client.searchIndex(query, 20).then((res) => {
      if (!mounted) return;
      setHits(res.hits as typeof hits);
    });
    return () => {
      mounted = false;
    };
  }, [client, query]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return hits;
    return hits.filter((h) => h.title.toLowerCase().includes(q) || h.snippet.toLowerCase().includes(q));
  }, [hits, query]);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4" data-testid="page-memory">
      <div className="text-xl font-semibold">{t("page.memory.title")}</div>
      <div className="rounded-2xl bg-foreground/5 p-4">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search"
          className="h-10 w-full rounded-xl bg-background px-3 text-sm outline-none"
          data-testid="memory-search"
        />

        <motion.div layout className="mt-3 grid gap-2">
          {filtered.map((h) => (
            <motion.details
              layout
              key={h.id}
              className="rounded-2xl bg-background p-3"
              data-testid={`memory-hit-${h.id}`}
            >
              <summary className="cursor-pointer list-none">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{h.title}</div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{h.snippet}</div>
                  </div>
                  <div className="text-xs text-muted-foreground">{h.score.toFixed(2)}</div>
                </div>
              </summary>
              <div className="mt-3 rounded-xl bg-foreground/5 p-3 text-xs text-muted-foreground">
                Full content, evidence, and versions will load on demand.
              </div>
            </motion.details>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
