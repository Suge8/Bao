export type DraftScheduleKind = "once" | "interval" | "cron";

export type TaskScheduleSpec = {
  kind: DraftScheduleKind;
  runAtTs?: number;
  intervalMs?: number;
  cron?: string;
  timezone?: string;
};

export type TaskSpec = {
  id: string;
  title: string;
  enabled: boolean;
  schedule: TaskScheduleSpec;
  action: {
    kind: "tool_call";
    toolCall: {
      dimsumId: string;
      toolName: string;
      args: {
        command?: string;
        args?: unknown;
      };
    };
  };
  policy: {
    timeoutMs: number;
    maxRetries: number;
  };
};

export type TaskDraft = {
  intent: string;
  confidence: number;
  missingFields: string[];
  draftSpec: TaskSpec | null;
};

export type BuildTaskDraftInput = {
  taskId: string;
  content: string;
  enabled: boolean;
  scheduleKind: DraftScheduleKind;
  runAtInput: string;
  intervalMinutesInput: string;
  defaultToolDimsumId: string;
  defaultToolName: string;
  defaultTimeoutMs: number;
  defaultMaxRetries: number;
};

export type ProvenanceKind = "user" | "ai" | "default";

export type DraftFieldPreview = {
  value: string;
  provenance: ProvenanceKind;
};

export type TaskDraftPreview = {
  title: DraftFieldPreview;
  schedule: DraftFieldPreview;
  tool: DraftFieldPreview;
  policy: DraftFieldPreview;
};

export function getTaskDraftPreview(draft: TaskDraft): TaskDraftPreview | null {
  if (!draft.draftSpec) return null;

  const spec = draft.draftSpec;
  
  // Format schedule
  let scheduleValue = "";
  if (spec.schedule.kind === "once") {
    const d = new Date((spec.schedule.runAtTs ?? 0) * 1000);
    scheduleValue = `Once at ${d.toLocaleString()}`;
  } else if (spec.schedule.kind === "interval") {
    scheduleValue = `Every ${Math.floor((spec.schedule.intervalMs ?? 0) / 60000)} mins`;
  } else {
    scheduleValue = spec.schedule.cron || "Cron";
  }

  // Format tool
  const toolName = spec.action.toolCall.toolName;
  const args = JSON.stringify(spec.action.toolCall.args);
  const toolValue = `${toolName} (${args})`;

  // Format policy
  const policyValue = `Timeout: ${spec.policy.timeoutMs}ms, Retries: ${spec.policy.maxRetries}`;

  return {
    title: {
      value: spec.title,
      provenance: "user",
    },
    schedule: {
      value: scheduleValue,
      provenance: "user",
    },
    tool: {
      value: toolValue,
      provenance: "ai", // Inferred from intent
    },
    policy: {
      value: policyValue,
      provenance: "default",
    },
  };
}

export const DRAFT_CONFIDENCE_THRESHOLD = 0.7;

export function buildDeterministicTaskDraft(input: BuildTaskDraftInput): TaskDraft {
  const intent = input.content.trim();
  const schedule = buildSchedule(input.scheduleKind, input.runAtInput, input.intervalMinutesInput);
  const draftSpec: TaskSpec | null = intent
    ? {
        id: input.taskId,
        title: intent,
        enabled: input.enabled,
        schedule,
        action: {
          kind: "tool_call",
          toolCall: {
            dimsumId: input.defaultToolDimsumId,
            toolName: input.defaultToolName,
            args: buildTaskToolArgs(intent),
          },
        },
        policy: {
          timeoutMs: input.defaultTimeoutMs,
          maxRetries: input.defaultMaxRetries,
        },
      }
    : null;

  const missingFields = draftSpec ? validateTaskSpecPrecheck(draftSpec) : ["title"];

  return {
    intent,
    confidence: missingFields.length === 0 ? 0.9 : 0.35,
    missingFields,
    draftSpec,
  };
}

export function isDraftReadyForSubmit(draft: TaskDraft): boolean {
  if (!draft.draftSpec) return false;
  if (draft.confidence < DRAFT_CONFIDENCE_THRESHOLD) return false;
  return draft.missingFields.length === 0;
}

export function validateTaskSpecPrecheck(spec: TaskSpec): string[] {
  const schemaIssues = validateTaskSpecSchemaPrecheck(spec);
  const businessIssues = validateTaskSpecBusinessPrecheck(spec);
  return [...new Set([...schemaIssues, ...businessIssues])];
}

function validateTaskSpecSchemaPrecheck(spec: TaskSpec): string[] {
  const issues: string[] = [];

  if (!spec.id.trim()) issues.push("id");
  if (!spec.title.trim()) issues.push("title");

  if (spec.schedule.kind === "once") {
    if (!Number.isInteger(spec.schedule.runAtTs) || (spec.schedule.runAtTs ?? 0) < 1) {
      issues.push("once.runAtTs");
    }
  }
  if (spec.schedule.kind === "interval") {
    if (!Number.isInteger(spec.schedule.intervalMs) || (spec.schedule.intervalMs ?? 0) < 1000) {
      issues.push("interval.intervalMs");
    }
  }
  if (spec.schedule.kind === "cron" && !spec.schedule.cron?.trim()) {
    issues.push("cron.cron");
  }

  if (!spec.action.toolCall.dimsumId.trim()) issues.push("action.toolCall.dimsumId");
  if (!spec.action.toolCall.toolName.trim()) issues.push("action.toolCall.toolName");

  return issues;
}

function validateTaskSpecBusinessPrecheck(spec: TaskSpec): string[] {
  const issues: string[] = [];

  if (!Number.isInteger(spec.schedule.runAtTs) && spec.schedule.kind === "once") {
    issues.push("once.runAtTs");
  }

  if (spec.schedule.kind === "interval" && (spec.schedule.intervalMs ?? 0) < 1000) {
    issues.push("interval.intervalMs");
  }

  if (!spec.action.toolCall.args?.command) {
    issues.push("tool.args.command");
  }

  if (spec.policy.maxRetries < 0 || spec.policy.maxRetries > 1) {
    issues.push("policy.maxRetries");
  }

  return issues;
}

function buildSchedule(
  scheduleKind: DraftScheduleKind,
  runAtInput: string,
  intervalMinutesInput: string,
): TaskScheduleSpec {
  if (scheduleKind === "interval") {
    const intervalMinutes = Number(intervalMinutesInput);
    return {
      kind: "interval",
      intervalMs: Number.isFinite(intervalMinutes) ? Math.floor(intervalMinutes * 60_000) : undefined,
    };
  }

  const runAtTs = runAtInput ? Math.floor(new Date(runAtInput).getTime() / 1000) : Math.floor(Date.now() / 1000);
  return {
    kind: "once",
    runAtTs: Number.isFinite(runAtTs) ? runAtTs : undefined,
  };
}

function buildTaskToolArgs(text: string): { command: string; args: string[] } {
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
