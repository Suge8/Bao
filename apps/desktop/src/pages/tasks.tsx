import { useI18n } from "@/i18n/i18n";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { ShinyButton } from "@/components/ui/shiny-button";
import { MagicCard } from "@/components/ui/magic-card";
import { Edit, Play, Power } from "lucide-react";

type TaskItem = {
  taskId: string;
  title: string;
  enabled: boolean;
  schedule?: {
    kind?: "once" | "interval" | "cron" | string;
    runAtTs?: number | null;
    intervalMs?: number | null;
    cron?: string | null;
    timezone?: string | null;
  };
  nextRunAt?: number | null;
  lastRunAt?: number | null;
  lastStatus?: string | null;
  lastError?: string | null;
  tool?: {
    dimsumId?: string;
    toolName?: string;
    args?: unknown;
  };
  policy?: {
    timeoutMs?: number;
    maxRetries?: number;
    killSwitchGroup?: string;
  } | null;
};

type ScheduleKind = "once" | "interval" | "cron";

const DEFAULT_TOOL_DIMSUM_ID = "bao.engine.default";
const DEFAULT_TOOL_NAME = "shell.exec";
const DEFAULT_TIMEOUT_MS = 1000;
const DEFAULT_MAX_RETRIES = 1;

export default function TasksPage() {
  const { t } = useI18n();
  const client = useClient();

  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [content, setContent] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [scheduleKind, setScheduleKind] = useState<ScheduleKind>("once");
  const [runAtInput, setRunAtInput] = useState("");
  const [intervalMinutesInput, setIntervalMinutesInput] = useState("60");
  const [showForm, setShowForm] = useState(false);

  const refreshTasks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.listTasks();
      setTasks((res.tasks as TaskItem[]) ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("tasks.error.load_failed"));
    } finally {
      setLoading(false);
    }
  }, [client, t]);

  useEffect(() => {
    void refreshTasks();
  }, [refreshTasks]);

  const items = useMemo(() => {
    return tasks.map((task) => ({
      id: task.taskId,
      kind: task.schedule?.kind ?? "once",
      title: task.title,
      enabled: task.enabled,
      nextRunAt: task.nextRunAt,
      lastRunAt: task.lastRunAt,
      lastStatus: task.lastStatus,
      lastError: task.lastError,
    }));
  }, [tasks]);

  const submitTask = async () => {
    const nextContent = content.trim();
    if (!nextContent) {
      setError(t("tasks.error.content_required"));
      return;
    }

    const id = editingTaskId ?? generateTaskId(nextContent);
    const runAtTs = runAtInput ? Math.floor(new Date(runAtInput).getTime() / 1000) : undefined;
    const intervalMinutes = Number(intervalMinutesInput);

    const schedule: Record<string, unknown> = { kind: scheduleKind };
    if (scheduleKind === "once") {
      schedule.runAtTs = Number.isFinite(runAtTs) ? runAtTs : Math.floor(Date.now() / 1000);
    }
    if (scheduleKind === "interval") {
      if (!Number.isFinite(intervalMinutes) || intervalMinutes < 1) {
        setError(t("tasks.error.interval_minutes_invalid"));
        return;
      }
      schedule.intervalMs = Math.floor(intervalMinutes * 60_000);
    }

    const spec = {
      id,
      title: nextContent,
      enabled,
      schedule,
      action: {
        kind: "tool_call",
        toolCall: {
          dimsumId: DEFAULT_TOOL_DIMSUM_ID,
          toolName: DEFAULT_TOOL_NAME,
          args: buildTaskToolArgs(nextContent),
        },
      },
      policy: {
        timeoutMs: DEFAULT_TIMEOUT_MS,
        maxRetries: DEFAULT_MAX_RETRIES,
      },
    };

    setSaving(true);
    setError(null);
    try {
      const saveTask = editingTaskId ? client.updateTask : client.createTask;
      await saveTask(spec);
      await refreshTasks();
      resetForm();
      setShowForm(false);
    } catch (err) {
      setError(toErrorMessage(err, t("tasks.error.save_failed")));
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setEditingTaskId(null);
    setContent("");
    setEnabled(true);
    setScheduleKind("once");
    setRunAtInput("");
    setIntervalMinutesInput("60");
  };

  const loadTaskForEdit = (id: string) => {
    const task = tasks.find((item) => item.taskId === id);
    if (!task) return;
    setEditingTaskId(task.taskId);
    setContent(task.title);
    setEnabled(task.enabled);

    const kind = task.schedule?.kind === "interval" ? "interval" : "once";
    setScheduleKind(kind);
    setRunAtInput(toDatetimeLocalInput(task.schedule?.runAtTs));
    setIntervalMinutesInput(String(intervalMsToMinutes(task.schedule?.intervalMs)));
    setShowForm(true);
  };

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col overflow-hidden" data-testid="page-tasks">
      <div className="flex items-center justify-between">
        <div className="text-xl font-bold tracking-tight">{t("page.tasks.title")}</div>
        <ShinyButton 
          type="button" 
          onClick={() => {
            resetForm();
            setShowForm(!showForm);
          }}
          className="h-9 rounded-xl px-4 text-sm font-medium"
        >
          {showForm ? t("tasks.form.cancel") : t("tasks.form.new_task")}
        </ShinyButton>
      </div>

      <div className="mt-6 min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
        <motion.div
          animate={{ height: showForm ? "auto" : 0, opacity: showForm ? 1 : 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden"
        >
        <MagicCard className="rounded-3xl border border-border/50 bg-background/60 backdrop-blur-xl">
          <div className="p-6">
            <div className="mb-2 text-sm font-semibold tracking-tight">
              {editingTaskId ? t("tasks.form.edit_title") : t("tasks.form.create_title")}
            </div>
            <div className="mb-4 text-xs text-muted-foreground">{t("tasks.form.helper")}</div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div className="col-span-full rounded-xl bg-muted/30 p-3 ring-1 ring-border/50 md:col-span-2 lg:col-span-3">
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t("tasks.form.content_label")}</div>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={t("tasks.form.content_placeholder")}
                  className="min-h-[92px] w-full resize-y rounded-lg bg-background px-3 py-2 text-sm outline-none ring-1 ring-border/50 focus:ring-primary/30"
                  data-testid="task-content-input"
                />
              </div>

              <SelectField
                label={t("tasks.form.schedule_type")}
                value={scheduleKind}
                onChange={(value) => setScheduleKind(value as ScheduleKind)}
                options={[
                  { value: "once", label: t("tasks.form.schedule_once") },
                  { value: "interval", label: t("tasks.form.schedule_interval") },
                ]}
              />

              <div className="space-y-1.5 rounded-xl bg-muted/30 p-3 ring-1 ring-border/50">
                <div className="text-xs font-medium text-muted-foreground">{t("tasks.form.status")}</div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setEnabled(true)}
                    className={cn(
                      "flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                      enabled ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted"
                    )}
                    >
                    {t("tasks.form.enabled")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEnabled(false)}
                    className={cn(
                      "flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                      !enabled ? "bg-muted text-foreground ring-1 ring-border shadow-sm" : "text-muted-foreground hover:bg-muted"
                    )}
                    >
                    {t("tasks.form.disabled")}
                  </button>
                </div>
              </div>

              {scheduleKind === "once" ? (
                <InputField
                  label={t("tasks.form.run_at")}
                  value={runAtInput}
                  onChange={setRunAtInput}
                  type="datetime-local"
                />
              ) : null}
              {scheduleKind === "interval" ? (
                <InputField
                  label={t("tasks.form.interval_minutes")}
                  value={intervalMinutesInput}
                  onChange={setIntervalMinutesInput}
                  type="number"
                />
              ) : null}
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              {error ? <div className="text-xs font-medium text-destructive">{error}</div> : null}
              {editingTaskId ? (
                <ShinyButton
                  type="button"
                  onClick={() => {
                    resetForm();
                    setShowForm(false);
                  }}
                  className="h-9 rounded-xl px-4 text-sm bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  {t("tasks.form.cancel")}
                </ShinyButton>
              ) : null}
              <ShinyButton
                type="button"
                onClick={() => {
                  void submitTask();
                }}
                disabled={saving}
                className="h-9 rounded-xl px-6 text-sm bg-primary text-primary-foreground hover:bg-primary/90"
              >
                {saving
                  ? t("tasks.form.saving")
                  : editingTaskId
                    ? t("tasks.form.update")
                    : t("tasks.form.create")}
              </ShinyButton>
            </div>
          </div>
        </MagicCard>
        </motion.div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((it) => (
            <MagicCard key={it.id} className="group overflow-hidden rounded-3xl border border-border/50 bg-background/60 backdrop-blur-sm transition-all hover:shadow-sm" data-testid={`task-item-${it.id}`}>
            <div className="flex h-full flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                      <div className={cn("h-2 w-2 rounded-full", it.enabled ? "bg-green-500" : "bg-muted-foreground/30")} />
                    <div className="truncate text-base font-semibold tracking-tight">{it.title}</div>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground/70">
                    <span className="font-mono">{it.id}</span>
                    <span>•</span>
                    <span className="capitalize">{it.kind}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    type="button"
                    onClick={() => loadTaskForEdit(it.id)}
                    className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <Edit className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const act = it.enabled ? client.disableTask : client.enableTask;
                      void act(it.id)
                        .then(() => refreshTasks())
                        .catch((err) => setError(toErrorMessage(err, t("tasks.error.toggle_failed"))));
                    }}
                    className={cn(
                      "rounded-lg p-1.5 hover:bg-muted",
                      it.enabled ? "text-green-500 hover:text-green-600" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <Power className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="mt-4 flex-1 space-y-2 text-xs text-muted-foreground/80">
                <div className="grid grid-cols-2 gap-2">
                   <div className="rounded-lg bg-muted/30 px-2 py-1.5">
                     <div className="text-[10px] uppercase tracking-wider opacity-70">{t("tasks.card.next_run")}</div>
                     <div className="mt-0.5 truncate font-medium text-foreground">{formatUnix(it.nextRunAt)}</div>
                   </div>
                   <div className="rounded-lg bg-muted/30 px-2 py-1.5">
                     <div className="text-[10px] uppercase tracking-wider opacity-70">{t("tasks.card.last_run")}</div>
                     <div className="mt-0.5 truncate font-medium text-foreground">{formatUnix(it.lastRunAt)}</div>
                   </div>
                </div>
                {it.lastStatus ? (
                  <div className="rounded-lg bg-muted/30 px-2 py-1.5">
                    <div className="text-[10px] uppercase tracking-wider opacity-70">{t("tasks.card.last_status")}</div>
                    <div className="mt-0.5 truncate font-medium text-foreground">{it.lastStatus}</div>
                  </div>
                ) : null}
                {it.lastError ? (
                  <div className="mt-2 rounded-lg bg-red-500/10 p-2 text-red-600 dark:text-red-400">
                    <div className="font-semibold">{t("tasks.card.error")}</div>
                    <div className="line-clamp-2">{it.lastError}</div>
                  </div>
                ) : null}
              </div>

              <div className="mt-4 pt-4 border-t border-border/50">
                <ShinyButton
                  type="button"
                  onClick={() => {
                    void client
                      .runTaskNow(it.id)
                      .then(() => refreshTasks())
                      .catch((err) => setError(toErrorMessage(err, t("tasks.error.run_failed"))));
                  }}
                  className="w-full h-8 rounded-xl text-xs font-medium"
                  data-testid={`task-run-${it.id}`}
                >
                  <span className="flex items-center justify-center gap-1.5">
                    <Play className="h-3 w-3" />
                    {t("tasks.card.run_now")}
                  </span>
                </ShinyButton>
              </div>
            </div>
          </MagicCard>
        ))}
        {!loading && items.length === 0 ? (
          <div className="col-span-full flex h-40 items-center justify-center rounded-3xl border border-dashed border-border/50 bg-muted/20 text-sm text-muted-foreground">
            {t("tasks.empty")}
          </div>
        ) : null}
        </div>
      </div>
    </div>
  );
}

function buildTaskToolArgs(text: string) {
  const escaped = text
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\$/g, "\\$")
    .replace(/`/g, "\\`");
  return {
    command: "sh",
    args: ["-lc", `echo \"${escaped}\"`],
  };
}

function generateTaskId(content: string): string {
  const normalized = content
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 24);
  const base = normalized || "task";
  return `${base}-${Date.now().toString(36)}`;
}

function intervalMsToMinutes(intervalMs?: number | null): number {
  if (!intervalMs || intervalMs < 60_000) return 60;
  return Math.max(1, Math.round(intervalMs / 60_000));
}

function toDatetimeLocalInput(runAtTs?: number | null): string {
  if (!runAtTs) {
    return "";
  }
  const date = new Date(runAtTs * 1000);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function toErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function InputField({
  label,
  value,
  onChange,
  type = "text",
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: "text" | "number" | "datetime-local";
  disabled?: boolean;
}) {
  return (
    <label className="space-y-1.5 rounded-xl bg-muted/30 p-3 ring-1 ring-border/50 focus-within:bg-muted/50 focus-within:ring-primary/30 transition-all">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={cn(
          "w-full bg-transparent text-sm font-medium outline-none placeholder:text-muted-foreground/50",
          disabled && "cursor-not-allowed opacity-60"
        )}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="space-y-1.5 rounded-xl bg-muted/30 p-3 ring-1 ring-border/50 focus-within:bg-muted/50 focus-within:ring-primary/30 transition-all">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent text-sm font-medium outline-none"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
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
