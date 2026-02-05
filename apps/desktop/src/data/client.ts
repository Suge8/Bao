import type { BaoEvent, UnlistenFn } from "./events";

export type DesktopClient = {
  onBaoEvent: (cb: (event: BaoEvent) => void) => Promise<UnlistenFn>;

  // Phase1 minimal surface. More will be added as UI pages become real.
  listSessions: () => Promise<{ sessions: { id: string; title: string }[] }>;

  listTasks: () => Promise<{ tasks: unknown[] }>;
  createTask: (spec: unknown) => Promise<{ ok: true }>;
  enableTask: (taskId: string) => Promise<{ ok: true }>;
  disableTask: (taskId: string) => Promise<{ ok: true }>;
  runTaskNow: (taskId: string) => Promise<{ ok: true }>;

  listMemories: () => Promise<{ memories: unknown[] }>;
  searchIndex: (query: string, limit?: number) => Promise<{ hits: unknown[] }>;
  getItems: (ids: string[]) => Promise<{ items: unknown[] }>;
  getTimeline: (namespace?: string) => Promise<{ timeline: unknown[] }>;
  applyMutationPlan: (plan: unknown) => Promise<{ ok: true }>;
  rollbackVersion: (memoryId: string, versionId: string) => Promise<{ ok: true }>;

  getSettings: () => Promise<{ settings: { key: string; value: unknown }[] }>;
  updateSettings: (key: string, value: unknown) => Promise<{ ok: true }>;
  generatePairingToken: () => Promise<{ token: string }>;
  gatewayStart: () => Promise<void>;
  gatewayStop: () => Promise<void>;
};
