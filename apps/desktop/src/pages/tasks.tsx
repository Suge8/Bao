import { useI18n } from "@/i18n/i18n";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import { useEffect, useMemo, useState } from "react";

export default function TasksPage() {
  const { t } = useI18n();
  const client = useClient();
  const [tasks, setTasks] = useState<
    { taskId: string; title: string; enabled: boolean; schedule?: { kind?: string } }[]
  >([]);

  useEffect(() => {
    let mounted = true;
    client.listTasks().then((res) => {
      if (!mounted) return;
      setTasks(res.tasks as typeof tasks);
    });
    return () => {
      mounted = false;
    };
  }, [client]);

  const items = useMemo(() => {
    return tasks.map((task) => ({
      id: task.taskId,
      kind: task.schedule?.kind ?? "once",
      title: task.title,
      enabled: task.enabled,
    }));
  }, [tasks]);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4" data-testid="page-tasks">
      <div className="text-xl font-semibold">{t("page.tasks.title")}</div>
      <div className="rounded-2xl bg-foreground/5 p-4">
        <motion.div layout className="grid gap-2">
          {items.map((it) => (
            <motion.div
              layout
              key={it.id}
              className="flex items-center justify-between rounded-2xl bg-background p-3"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{it.title}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {it.kind} {it.enabled ? "" : "· disabled"}
                </div>
              </div>
              <button
                type="button"
                onClick={() => client.runTaskNow(it.id)}
                className="rounded-xl bg-foreground/5 px-3 py-2 text-xs transition hover:bg-foreground/10"
                data-testid={`task-run-${it.id}`}
              >
                Run
              </button>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
