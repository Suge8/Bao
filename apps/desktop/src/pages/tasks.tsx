import { useI18n } from "@/i18n/i18n";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";

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

  const refreshTasks = async () => {
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
  };

  useEffect(() => {
    void refreshTasks();
  }, [client]);

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
      const iso = new Date(task.schedule.runAtTs * 1000).toISOString().slice(0, 16);
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
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4" data-testid="page-tasks">
      <div className="text-xl font-semibold">{t("page.tasks.title")}</div>

      <div className="rounded-2xl bg-foreground/5 p-4">
        <div className="text-sm font-medium">{editingTaskId ? "编辑任务" : "新建任务"}</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <InputField label="任务 ID" value={taskId} onChange={setTaskId} disabled={Boolean(editingTaskId)} />
          <InputField label="任务标题" value={title} onChange={setTitle} />

          <SelectField
            label="调度类型"
            value={scheduleKind}
            onChange={(value) => setScheduleKind(value as ScheduleKind)}
            options={[
              { value: "once", label: "once" },
              { value: "interval", label: "interval" },
              { value: "cron", label: "cron" },
            ]}
          />

          <div className="rounded-xl bg-background p-3">
            <div className="text-xs text-muted-foreground">启用状态</div>
            <div className="mt-2 flex gap-2 text-sm">
              <button
                type="button"
                onClick={() => setEnabled(true)}
                className={cn(
                  "rounded-lg px-3 py-1.5 transition",
                  enabled ? "bg-foreground text-background" : "bg-foreground/10",
                )}
              >
                enabled
              </button>
              <button
                type="button"
                onClick={() => setEnabled(false)}
                className={cn(
                  "rounded-lg px-3 py-1.5 transition",
                  !enabled ? "bg-foreground text-background" : "bg-foreground/10",
                )}
              >
                disabled
              </button>
            </div>
          </div>

          {scheduleKind === "once" ? (
            <InputField
              label="runAt (local datetime)"
              value={runAtInput}
              onChange={setRunAtInput}
              type="datetime-local"
            />
          ) : null}
          {scheduleKind === "interval" ? (
            <InputField
              label="intervalMs"
              value={intervalMsInput}
              onChange={setIntervalMsInput}
              type="number"
            />
          ) : null}
          {scheduleKind === "cron" ? (
            <>
              <InputField label="cron" value={cronInput} onChange={setCronInput} />
              <InputField label="timezone" value={timezone} onChange={setTimezone} />
            </>
          ) : null}

          <InputField label="tool.dimsumId" value={toolDimsumId} onChange={setToolDimsumId} />
          <InputField label="tool.toolName" value={toolName} onChange={setToolName} />

          <InputField
            label="policy.timeoutMs"
            value={timeoutMsInput}
            onChange={setTimeoutMsInput}
            type="number"
          />
          <InputField
            label="policy.maxRetries"
            value={maxRetriesInput}
            onChange={setMaxRetriesInput}
            type="number"
          />

          <InputField label="policy.killSwitchGroup" value={killSwitchGroup} onChange={setKillSwitchGroup} />

          <div className="rounded-xl bg-background p-3 md:col-span-2">
            <div className="text-xs text-muted-foreground">tool.args (JSON)</div>
            <textarea
              value={toolArgsInput}
              onChange={(e) => setToolArgsInput(e.target.value)}
              className="mt-2 h-32 w-full rounded-xl bg-foreground/5 p-3 text-xs outline-none"
            />
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void submitTask();
            }}
            disabled={saving}
            className={cn(
              "rounded-xl px-4 py-2 text-sm transition",
              saving
                ? "cursor-not-allowed bg-foreground/10 text-muted-foreground"
                : "bg-foreground text-background hover:opacity-90",
            )}
          >
            {saving ? "保存中" : editingTaskId ? "更新任务" : "创建任务"}
          </button>
          {editingTaskId ? (
            <button
              type="button"
              onClick={resetForm}
              className="rounded-xl bg-foreground/10 px-4 py-2 text-sm transition hover:bg-foreground/20"
            >
              取消编辑
            </button>
          ) : null}
          {error ? <div className="text-xs text-red-500">{error}</div> : null}
        </div>
      </div>

      <div className="rounded-2xl bg-foreground/5 p-4">
        <div className="mb-2 text-sm font-medium">任务列表</div>
        {loading ? <div className="text-sm text-muted-foreground">加载中...</div> : null}
        <motion.div layout className="grid gap-2">
          {items.map((it) => (
            <motion.div
              layout
              key={it.id}
              className="rounded-2xl bg-background p-3"
              data-testid={`task-item-${it.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{it.title}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {it.id} · {it.kind} · {it.enabled ? "enabled" : "disabled"}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    tool: {it.toolDimsumId}/{it.toolName}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    next: {formatUnix(it.nextRunAt)} · last: {formatUnix(it.lastRunAt)} · status: {it.lastStatus ?? "-"}
                  </div>
                  {it.lastError ? <div className="mt-1 text-xs text-red-500">{it.lastError}</div> : null}
                </div>
                <div className="flex shrink-0 gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => loadTaskForEdit(it.id)}
                    className="rounded-xl bg-foreground/10 px-3 py-2 transition hover:bg-foreground/20"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const act = it.enabled ? client.disableTask : client.enableTask;
                      void act(it.id)
                        .then(() => refreshTasks())
                        .catch((err) => setError(err instanceof Error ? err.message : "切换失败"));
                    }}
                    className="rounded-xl bg-foreground/10 px-3 py-2 transition hover:bg-foreground/20"
                  >
                    {it.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      void client
                        .runTaskNow(it.id)
                        .then(() => refreshTasks())
                        .catch((err) => setError(err instanceof Error ? err.message : "执行失败"));
                    }}
                    className="rounded-xl bg-foreground/10 px-3 py-2 transition hover:bg-foreground/20"
                    data-testid={`task-run-${it.id}`}
                  >
                    Run
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
          {!loading && items.length === 0 ? (
            <div className="rounded-xl bg-background p-3 text-sm text-muted-foreground">暂无任务</div>
          ) : null}
        </motion.div>
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
    <label className="rounded-xl bg-background p-3 text-xs text-muted-foreground">
      <div>{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={cn(
          "mt-2 h-10 w-full rounded-xl bg-foreground/5 px-3 text-sm text-foreground outline-none",
          disabled && "cursor-not-allowed opacity-60",
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
    <label className="rounded-xl bg-background p-3 text-xs text-muted-foreground">
      <div>{label}</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 h-10 w-full rounded-xl bg-foreground/5 px-3 text-sm text-foreground outline-none"
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
  return d.toLocaleString();
}
