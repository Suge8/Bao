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

export default function TasksPage() {
  const { t } = useI18n();
  const client = useClient();

  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [taskId, setTaskId] = useState("");
  const [title, setTitle] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [scheduleKind, setScheduleKind] = useState<ScheduleKind>("once");
  const [runAtInput, setRunAtInput] = useState("");
  const [intervalMsInput, setIntervalMsInput] = useState("60000");
  const [cronInput, setCronInput] = useState("*/5 * * * *");
  const [timezone, setTimezone] = useState("UTC");
  const [toolDimsumId, setToolDimsumId] = useState("bao.engine.default");
  const [toolName, setToolName] = useState("shell.exec");
  const [toolArgsInput, setToolArgsInput] = useState('{"command":"sh","args":["-lc","echo bao-task-ok"]}');
  const [timeoutMsInput, setTimeoutMsInput] = useState("1000");
  const [maxRetriesInput, setMaxRetriesInput] = useState("1");
  const [killSwitchGroup, setKillSwitchGroup] = useState("");
  const [showForm, setShowForm] = useState(false);

  const refreshTasks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.listTasks();
      setTasks((res.tasks as TaskItem[]) ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "任务加载失败");
    } finally {
      setLoading(false);
    }
  }, [client]);

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
      toolDimsumId: task.tool?.dimsumId ?? "",
      toolName: task.tool?.toolName ?? "",
    }));
  }, [tasks]);

  const submitTask = async () => {
    const id = taskId.trim();
    const nextTitle = title.trim();
    if (!id || !nextTitle) {
      setError("任务 ID 和标题不能为空");
      return;
    }

    let args: unknown;
    try {
      args = JSON.parse(toolArgsInput || "null");
    } catch {
      setError("工具参数不是合法 JSON");
      return;
    }

    const argsObj = args && typeof args === "object" ? (args as Record<string, unknown>) : null;
    const commandValue = argsObj?.command;
    if (typeof commandValue !== "string" || commandValue.trim().length === 0) {
      setError("工具参数必须包含 command 字段（字符串）");
      return;
    }

    const timeoutMs = Number(timeoutMsInput);
    const maxRetries = Number(maxRetriesInput);
    const runAtTs = runAtInput ? Math.floor(new Date(runAtInput).getTime() / 1000) : undefined;
    const intervalMs = Number(intervalMsInput);

    const schedule: Record<string, unknown> = { kind: scheduleKind };
    if (scheduleKind === "once") {
      schedule.runAtTs = Number.isFinite(runAtTs) ? runAtTs : Math.floor(Date.now() / 1000);
    }
    if (scheduleKind === "interval") {
      if (!Number.isFinite(intervalMs) || intervalMs < 1000) {
        setError("intervalMs 必须是 >= 1000 的整数");
        return;
      }
      schedule.intervalMs = Math.floor(intervalMs);
    }
    if (scheduleKind === "cron") {
      if (!cronInput.trim()) {
        setError("cron 表达式不能为空");
        return;
      }
      schedule.cron = cronInput.trim();
      if (timezone.trim()) {
        schedule.timezone = timezone.trim();
      }
    }

    const spec = {
      id,
      title: nextTitle,
      enabled,
      schedule,
      action: {
        kind: "tool_call",
        toolCall: {
          dimsumId: toolDimsumId.trim(),
          toolName: toolName.trim(),
          args,
        },
      },
      policy: {
        timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? Math.floor(timeoutMs) : undefined,
        maxRetries: Number.isFinite(maxRetries) && maxRetries >= 0 ? Math.floor(maxRetries) : undefined,
        killSwitchGroup: killSwitchGroup.trim() || undefined,
      },
    };

    setSaving(true);
    setError(null);
    try {
      if (editingTaskId) {
        await client.updateTask(spec);
      } else {
        await client.createTask(spec);
      }
      await refreshTasks();
      resetForm();
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "任务保存失败");
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setEditingTaskId(null);
    setTaskId("");
    setTitle("");
    setEnabled(true);
    setScheduleKind("once");
    setRunAtInput("");
    setIntervalMsInput("60000");
    setCronInput("*/5 * * * *");
    setTimezone("UTC");
    setToolDimsumId("bao.engine.default");
    setToolName("shell.exec");
    setToolArgsInput('{"command":"sh","args":["-lc","echo bao-task-ok"]}');
    setTimeoutMsInput("1000");
    setMaxRetriesInput("1");
    setKillSwitchGroup("");
  };

  const loadTaskForEdit = (id: string) => {
    const task = tasks.find((item) => item.taskId === id);
    if (!task) return;
    setEditingTaskId(task.taskId);
    setTaskId(task.taskId);
    setTitle(task.title);
    setEnabled(task.enabled);

    const kind = (task.schedule?.kind ?? "once") as ScheduleKind;
    setScheduleKind(kind);
    if (task.schedule?.runAtTs) {
      const date = new Date(task.schedule.runAtTs * 1000);
      const iso = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      setRunAtInput(iso);
    } else {
      setRunAtInput("");
    }
    setIntervalMsInput(String(task.schedule?.intervalMs ?? 60000));
    setCronInput(task.schedule?.cron ?? "*/5 * * * *");
    setTimezone(task.schedule?.timezone ?? "UTC");
    setToolDimsumId(task.tool?.dimsumId ?? "bao.engine.default");
    setToolName(task.tool?.toolName ?? "shell.exec");
    setToolArgsInput(
      JSON.stringify(task.tool?.args ?? { command: "sh", args: ["-lc", "echo bao-task-ok"] }, null, 2),
    );
    setTimeoutMsInput(String(task.policy?.timeoutMs ?? 1000));
    setMaxRetriesInput(String(task.policy?.maxRetries ?? 1));
    setKillSwitchGroup(task.policy?.killSwitchGroup ?? "");
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
          {showForm ? "Cancel" : "New Task"}
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
            <div className="mb-4 text-sm font-semibold tracking-tight">{editingTaskId ? "Edit Task" : "Create Task"}</div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <InputField label="Task ID" value={taskId} onChange={setTaskId} disabled={Boolean(editingTaskId)} />
              <InputField label="Title" value={title} onChange={setTitle} />

              <SelectField
                label="Schedule Type"
                value={scheduleKind}
                onChange={(value) => setScheduleKind(value as ScheduleKind)}
                options={[
                  { value: "once", label: "Once" },
                  { value: "interval", label: "Interval" },
                  { value: "cron", label: "Cron" },
                ]}
              />

              <div className="space-y-1.5 rounded-xl bg-muted/30 p-3 ring-1 ring-border/50">
                <div className="text-xs font-medium text-muted-foreground">Status</div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setEnabled(true)}
                    className={cn(
                      "flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                      enabled ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted"
                    )}
                  >
                    Enabled
                  </button>
                  <button
                    type="button"
                    onClick={() => setEnabled(false)}
                    className={cn(
                      "flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                      !enabled ? "bg-muted text-foreground ring-1 ring-border shadow-sm" : "text-muted-foreground hover:bg-muted"
                    )}
                  >
                    Disabled
                  </button>
                </div>
              </div>

              {scheduleKind === "once" ? (
                <InputField
                  label="Run At (Local)"
                  value={runAtInput}
                  onChange={setRunAtInput}
                  type="datetime-local"
                />
              ) : null}
              {scheduleKind === "interval" ? (
                <InputField
                  label="Interval (ms)"
                  value={intervalMsInput}
                  onChange={setIntervalMsInput}
                  type="number"
                />
              ) : null}
              {scheduleKind === "cron" ? (
                <>
                  <InputField label="Cron Expression" value={cronInput} onChange={setCronInput} />
                  <InputField label="Timezone" value={timezone} onChange={setTimezone} />
                </>
              ) : null}

              <InputField label="Tool Dimsum ID" value={toolDimsumId} onChange={setToolDimsumId} />
              <InputField label="Tool Name" value={toolName} onChange={setToolName} />

              <InputField
                label="Timeout (ms)"
                value={timeoutMsInput}
                onChange={setTimeoutMsInput}
                type="number"
              />
              <InputField
                label="Max Retries"
                value={maxRetriesInput}
                onChange={setMaxRetriesInput}
                type="number"
              />

              <InputField label="Kill Switch Group" value={killSwitchGroup} onChange={setKillSwitchGroup} />

              <div className="col-span-full rounded-xl bg-muted/30 p-3 ring-1 ring-border/50 md:col-span-2 lg:col-span-3">
                <div className="mb-2 text-xs font-medium text-muted-foreground">Tool Args (JSON)</div>
                <textarea
                  value={toolArgsInput}
                  onChange={(e) => setToolArgsInput(e.target.value)}
                  className="min-h-[100px] w-full resize-y rounded-lg bg-background px-3 py-2 text-xs font-mono outline-none ring-1 ring-border/50 focus:ring-primary/30"
                />
              </div>
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
                  Cancel
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
                {saving ? "Saving..." : editingTaskId ? "Update Task" : "Create Task"}
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
                        .catch((err) => setError(err instanceof Error ? err.message : "Toggle failed"));
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
                <div className="flex items-center gap-2 rounded-lg bg-muted/30 px-2 py-1.5">
                  <div className="font-medium text-foreground">Tool:</div>
                  <div className="truncate font-mono">{it.toolDimsumId}/{it.toolName}</div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                   <div className="rounded-lg bg-muted/30 px-2 py-1.5">
                     <div className="text-[10px] uppercase tracking-wider opacity-70">Next Run</div>
                     <div className="mt-0.5 truncate font-medium text-foreground">{formatUnix(it.nextRunAt)}</div>
                   </div>
                   <div className="rounded-lg bg-muted/30 px-2 py-1.5">
                     <div className="text-[10px] uppercase tracking-wider opacity-70">Last Run</div>
                     <div className="mt-0.5 truncate font-medium text-foreground">{formatUnix(it.lastRunAt)}</div>
                   </div>
                </div>
                {it.lastError ? (
                  <div className="mt-2 rounded-lg bg-red-500/10 p-2 text-red-600 dark:text-red-400">
                    <div className="font-semibold">Error:</div>
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
                      .catch((err) => setError(err instanceof Error ? err.message : "Run failed"));
                  }}
                  className="w-full h-8 rounded-xl text-xs font-medium"
                  data-testid={`task-run-${it.id}`}
                >
                  <span className="flex items-center justify-center gap-1.5">
                    <Play className="h-3 w-3" />
                    Run Now
                  </span>
                </ShinyButton>
              </div>
            </div>
          </MagicCard>
        ))}
        {!loading && items.length === 0 ? (
          <div className="col-span-full flex h-40 items-center justify-center rounded-3xl border border-dashed border-border/50 bg-muted/20 text-sm text-muted-foreground">
            No tasks found. Create one to get started.
          </div>
        ) : null}
        </div>
      </div>
    </div>
  );
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
