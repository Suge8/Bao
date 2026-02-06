import type { BaoEvent, UnlistenFn } from "./events";

export type DesktopClient = {
  onBaoEvent: (cb: (event: BaoEvent) => void) => Promise<UnlistenFn>;

  listSessions: () => Promise<{ sessions: { id: string; title: string }[] }>;
  createSession: (sessionId: string, title?: string) => Promise<{ ok: true }>;
  sendMessage: (sessionId: string, text: string) => Promise<{ ok: true }>;
  runEngineTurn: (
    sessionId: string,
    text: string,
  ) => Promise<{
    output: string;
    matched: boolean;
    needsMemory: boolean;
    toolName?: string;
    toolTriggered: boolean;
    toolOk?: boolean;
  }>;
  mcpListTools: (server: unknown) => Promise<{ tools?: unknown[]; transport?: string }>;
  mcpCallTool: (
    server: unknown,
    name: string,
    argumentsValue?: unknown,
  ) => Promise<{ result?: unknown; transport?: string }>;
  resourceList: (namespace: string, prefix?: string) => Promise<{ items?: unknown[] }>;
  resourceRead: (namespace: string, path: string) => Promise<Record<string, unknown>>;

  listTasks: () => Promise<{ tasks: unknown[] }>;
  listDimsums: () => Promise<{ dimsums: unknown[] }>;
  createTask: (spec: unknown) => Promise<{ ok: true }>;
  updateTask: (spec: unknown) => Promise<{ ok: true }>;
  enableTask: (taskId: string) => Promise<{ ok: true }>;
  disableTask: (taskId: string) => Promise<{ ok: true }>;
  runTaskNow: (taskId: string) => Promise<{ ok: true }>;
  enableDimsum: (dimsumId: string) => Promise<{ ok: true }>;
  disableDimsum: (dimsumId: string) => Promise<{ ok: true }>;

  listMemories: () => Promise<{ memories: unknown[] }>;
  searchIndex: (query: string, limit?: number) => Promise<{ hits: unknown[] }>;
  getItems: (ids: string[]) => Promise<{ items: unknown[] }>;
  getTimeline: (namespace?: string) => Promise<{ timeline: unknown[] }>;
  listMemoryVersions: (memoryId: string) => Promise<{ versions: unknown[] }>;
  applyMutationPlan: (plan: unknown) => Promise<{ ok: true }>;
  rollbackVersion: (memoryId: string, versionId: string) => Promise<{ ok: true }>;

  getSettings: () => Promise<{ settings: { key: string; value: unknown }[] }>;
  updateSettings: (key: string, value: unknown) => Promise<{ ok: true }>;
  generatePairingToken: () => Promise<{ token: string }>;
  gatewayStart: () => Promise<void>;
  gatewayStop: () => Promise<void>;
  gatewaySetAllowLan: (allow: boolean) => Promise<void>;
  killSwitchStopAll: () => Promise<void>;
};
