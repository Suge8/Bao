// @ts-nocheck
import { describe, expect, it } from "vitest";
import {
  DRAFT_CONFIDENCE_THRESHOLD,
  buildDeterministicTaskDraft,
  isDraftReadyForSubmit,
} from "./tasks-nl-draft";

describe("tasks nl draft", () => {
  it("builds a valid deterministic draft", () => {
    const draft = buildDeterministicTaskDraft({
      taskId: "task-1",
      content: "每晚归档日志",
      enabled: true,
      scheduleKind: "once",
      runAtInput: "2026-02-10T10:30",
      intervalMinutesInput: "60",
      defaultToolDimsumId: "bao.engine.default",
      defaultToolName: "shell.exec",
      defaultTimeoutMs: 1000,
      defaultMaxRetries: 1,
    });

    expect(draft.intent).toBe("每晚归档日志");
    expect(draft.confidence).toBeGreaterThanOrEqual(DRAFT_CONFIDENCE_THRESHOLD);
    expect(draft.missingFields).toEqual([]);
    expect(draft.draftSpec?.schedule.kind).toBe("once");
    expect(draft.draftSpec?.schedule.runAtTs).toBeGreaterThan(0);
    expect(isDraftReadyForSubmit(draft)).toBe(true);
  });

  it("blocks submit when draft confidence is low", () => {
    const draft = buildDeterministicTaskDraft({
      taskId: "task-2",
      content: "   ",
      enabled: true,
      scheduleKind: "once",
      runAtInput: "",
      intervalMinutesInput: "60",
      defaultToolDimsumId: "bao.engine.default",
      defaultToolName: "shell.exec",
      defaultTimeoutMs: 1000,
      defaultMaxRetries: 1,
    });

    expect(draft.confidence).toBeLessThan(DRAFT_CONFIDENCE_THRESHOLD);
    expect(draft.missingFields).toContain("title");
    expect(isDraftReadyForSubmit(draft)).toBe(false);
  });

  it("generates preview with correct provenance", () => {
    const draft = buildDeterministicTaskDraft({
      taskId: "task-preview-test",
      content: "Backup logs",
      enabled: true,
      scheduleKind: "once",
      runAtInput: "2026-03-10T10:00",
      intervalMinutesInput: "60",
      defaultToolDimsumId: "bao.engine.default",
      defaultToolName: "shell.exec",
      defaultTimeoutMs: 1000,
      defaultMaxRetries: 1,
    });

    // Mock the date to ensure deterministic output if needed, but here we just check structure
    const preview = getTaskDraftPreview(draft);
    expect(preview).not.toBeNull();
    
    if (preview) {
      expect(preview.title.value).toBe("Backup logs");
      expect(preview.title.provenance).toBe("user");

      expect(preview.schedule.provenance).toBe("user");
      // value check might be locale dependent, just check it contains expected parts
      expect(preview.schedule.value).toContain("Once at"); 
      
      expect(preview.tool.value).toContain("shell.exec");
      expect(preview.tool.provenance).toBe("ai");

      expect(preview.policy.value).toContain("Timeout: 1000ms");
      expect(preview.policy.provenance).toBe("default");
    }
  });

  it("returns null preview for invalid draft", () => {
     // Create a draft with no spec (empty content implies intent="" -> spec=null)
     const draft = buildDeterministicTaskDraft({
      taskId: "task-invalid",
      content: "", 
      enabled: true,
      scheduleKind: "once",
      runAtInput: "",
      intervalMinutesInput: "60",
      defaultToolDimsumId: "bao",
      defaultToolName: "exec",
      defaultTimeoutMs: 1000,
      defaultMaxRetries: 1,
    });
    
    const preview = getTaskDraftPreview(draft);
    expect(preview).toBeNull();
  });
});
