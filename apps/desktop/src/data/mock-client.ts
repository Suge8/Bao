import type { BaoEvent } from "./events";
import type { DesktopClient } from "./client";

function nowTs(): number {
  return Date.now();
}

export function createMockClient(): DesktopClient {
  let nextEventId = 1;
  const listeners = new Set<(event: BaoEvent) => void>();

  const emit = (type: string, payload: unknown) => {
    const event: BaoEvent = { eventId: nextEventId++, type, ts: nowTs(), payload };
    for (const cb of listeners) cb(event);
  };

  // Emit a deterministic boot event.
  queueMicrotask(() => emit("app.boot", { stage: 1 }));

  return {
    async onBaoEvent(cb) {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },

    async listSessions() {
      // Keep it stable for E2E selectors.
      const sessions = [
        { id: "s1", title: "Session 1" },
        { id: "s2", title: "Session 2" },
        { id: "s3", title: "Session 3" },
      ];
      emit("sessions.list", { sessions });
      return { sessions };
    },

    async listTasks() {
      const tasks = [
        { taskId: "t1", title: "One-shot reminder", enabled: true },
        { taskId: "t2", title: "Heartbeat task", enabled: true },
        { taskId: "t3", title: "Cron task", enabled: false },
      ];
      emit("tasks.list", { tasks });
      return { tasks };
    },

    async createTask() {
      emit("tasks.create", { ok: true });
      return { ok: true };
    },

    async enableTask(taskId) {
      emit("tasks.enable", { taskId, enabled: true });
      return { ok: true };
    },

    async disableTask(taskId) {
      emit("tasks.disable", { taskId, enabled: false });
      return { ok: true };
    },

    async runTaskNow(taskId) {
      emit("tasks.runNow", { taskId });
      return { ok: true };
    },

    async listMemories() {
      const memories = [
        { id: "m1", title: "User prefers zh", namespace: "pref", score: 0.92 },
        { id: "m2", title: "Device paired", namespace: "device", score: 0.81 },
      ];
      emit("memories.list", { memories });
      return { memories };
    },

    async searchIndex(query) {
      const hits = [
        { id: "m1", title: "User prefers zh", snippet: "locale=zh", score: 0.92, query },
      ];
      emit("memory.searchIndex", { query, hits });
      return { hits };
    },

    async getItems(ids) {
      const items = ids.map((id) => ({ id, title: "Mock item" }));
      emit("memory.getItems", { ids, items });
      return { items };
    },

    async getTimeline(namespace) {
      const timeline = [
        { namespace: namespace ?? "default", count: 1, updatedAt: nowTs() },
      ];
      emit("memory.getTimeline", { namespace, timeline });
      return { timeline };
    },

    async applyMutationPlan() {
      emit("memory.applyMutationPlan", { ok: true });
      return { ok: true };
    },

    async rollbackVersion(memoryId, versionId) {
      emit("memory.rollbackVersion", { memoryId, versionId });
      return { ok: true };
    },
  };
}
