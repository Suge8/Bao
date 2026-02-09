import { useI18n } from "@/i18n/i18n";
import { useClient } from "@/data/use-client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { ShinyButton } from "@/components/ui/shiny-button";
import { MagicCard } from "@/components/ui/magic-card";
import { Edit, Play, Power } from "lucide-react";
import {
  DRAFT_CONFIDENCE_THRESHOLD,
  buildDeterministicTaskDraft,
  isDraftReadyForSubmit,
  getTaskDraftPreview,
  type TaskDraft,
  type TaskDraftPreview,
} from "./tasks-nl-draft";

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
  const [taskDraft, setTaskDraft] = useState<TaskDraft | null>(null);

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

  useEffect(() => {
    if (!showForm) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [showForm]);

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
    const draft = buildDeterministicTaskDraft({
      taskId: editingTaskId ?? generateTaskId(nextContent || "task"),
      content,
      enabled,
      scheduleKind,
      runAtInput,
      intervalMinutesInput,
      defaultToolDimsumId: DEFAULT_TOOL_DIMSUM_ID,
      defaultToolName: DEFAULT_TOOL_NAME,
      defaultTimeoutMs: DEFAULT_TIMEOUT_MS,
      defaultMaxRetries: DEFAULT_MAX_RETRIES,
    });
    setTaskDraft(draft);

    if (!isDraftReadyForSubmit(draft)) {
      if (draft.confidence < DRAFT_CONFIDENCE_THRESHOLD) {
        setError("草案置信度过低，请先完善字段并重新生成草案");
        return;
      }
      setError(`草案校验失败: ${draft.missingFields.join(", ")}`);
      return;
    }

    const spec = draft.draftSpec;
    if (!spec) {
      setError(t("tasks.error.save_failed"));
      return;
    }

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
    setTaskDraft(null);
  };

  const generateDraft = () => {
    const draft = buildDeterministicTaskDraft({
      taskId: editingTaskId ?? generateTaskId(content.trim() || "task"),
      content,
      enabled,
      scheduleKind,
      runAtInput,
      intervalMinutesInput,
      defaultToolDimsumId: DEFAULT_TOOL_DIMSUM_ID,
      defaultToolName: DEFAULT_TOOL_NAME,
      defaultTimeoutMs: DEFAULT_TIMEOUT_MS,
      defaultMaxRetries: DEFAULT_MAX_RETRIES,
    });

    setTaskDraft(draft);
    if (draft.missingFields.length > 0) {
      setError(`草案校验失败: ${draft.missingFields.join(", ")}`);
      return;
    }
    setError(null);
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
            setError(null);
            setShowForm(true);
          }}
          className="h-9 rounded-xl px-4 text-sm font-medium"
        >
          {t("tasks.form.new_task")}
        </ShinyButton>
      </div>

      <div className="mt-6 min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
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

      {showForm ? (
        <button
          type="button"
          className="fixed inset-0 z-50 flex cursor-pointer items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              resetForm();
              setShowForm(false);
            }
          }}
          data-testid="tasks-create-modal-overlay"
        >
          <div className="w-full max-w-3xl cursor-default overflow-hidden rounded-3xl" data-testid="tasks-create-modal">
            <MagicCard className="rounded-3xl border border-border/50 bg-background/95 backdrop-blur-xl">
              <div className="max-h-[85vh] overflow-y-auto p-6">
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
                  <ShinyButton
                    type="button"
                    onClick={generateDraft}
                    className="h-9 rounded-xl px-4 text-sm bg-muted/50 text-foreground hover:bg-muted"
                    data-testid="tasks-generate-draft"
                  >
                    生成草案
                  </ShinyButton>
                  {taskDraft ? (
                    <div className="mr-auto rounded-lg bg-muted/30 px-3 py-2 text-xs text-muted-foreground" data-testid="tasks-draft-state">
                      <span className="font-medium text-foreground">intent:</span> {taskDraft.intent || "-"} ·{" "}
                      <span className="font-medium text-foreground">confidence:</span> {taskDraft.confidence.toFixed(2)} ·{" "}
                      <span className="font-medium text-foreground">missing:</span>{" "}
                      {taskDraft.missingFields.length > 0 ? taskDraft.missingFields.join(", ") : "none"}
                    </div>
                  ) : null}
                  {error ? <div className="text-xs font-medium text-destructive">{error}</div> : null}
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
          </div>
        </button>
      ) : null}
    </div>
  );
}

    </div>
  );
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

function ProvenanceBadge({ kind }: { kind: "user" | "ai" | "default" }) {
  const { t } = useI18n();
  const styles = {
    user: "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400",
    ai: "border-purple-500/30 bg-purple-500/10 text-purple-700 dark:text-purple-400",
    default: "border-border/50 bg-muted text-muted-foreground",
  };
  const labels = {
    user: t("tasks.source.user"),
    ai: t("tasks.source.ai"),
    default: t("tasks.source.default"),
  };

  return (
    <span className={cn("inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide", styles[kind])}>
      {labels[kind]}
    </span>
  );
}

function DraftPreviewPanel({ draft }: { draft: TaskDraft }) {
  const { t } = useI18n();
  const preview = useMemo(() => getTaskDraftPreview(draft), [draft]);
  if (!preview) return null;

  const fields = [
    { key: "title", label: t("tasks.preview.label.title"), ...preview.title, testId: "tasks-source-label-title" },
    { key: "schedule", label: t("tasks.preview.label.schedule"), ...preview.schedule, testId: "tasks-source-label-schedule" },
    { key: "tool", label: t("tasks.preview.label.tool"), ...preview.tool, testId: "tasks-source-label-tool" },
    { key: "policy", label: t("tasks.preview.label.policy"), ...preview.policy, testId: "tasks-source-label-policy" },
  ];

  return (
    <div className="mt-6 rounded-xl border border-border/50 bg-muted/20 p-4" data-testid="tasks-draft-preview">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("tasks.preview.title")}</div>
        <div className="flex gap-2 text-[10px] text-muted-foreground/60">
          <div>intent: {draft.intent || "-"}</div>
          <div>conf: {draft.confidence.toFixed(2)}</div>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((f) => (
          <div key={f.key} className="space-y-1 rounded-lg bg-background/50 p-2.5 ring-1 ring-border/30">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[10px] font-medium text-muted-foreground">{f.label}</div>
              <ProvenanceBadge kind={f.provenance} />
            </div>
            <div className="truncate text-sm font-medium" title={f.value} data-testid={f.testId}>
              {f.value || "-"}
            </div>
          </div>
        ))}
      </div>
      {draft.missingFields.length > 0 ? (
        <div className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400">
          Missing: {draft.missingFields.join(", ")}
        </div>
      ) : null}
    </div>
  );
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
