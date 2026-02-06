import { readFile } from "node:fs/promises";

export type GateStatus = "pass" | "fail";

export type GateLevel = "P0" | "P1" | "P2";

export type Gate = {
  gateId: string;
  level: GateLevel;
  command: string;
  status: GateStatus;
  evidence: string;
};

export type GateConfig = {
  version: string;
  gates: Gate[];
};

export type GateSummary = {
  results: Array<Pick<Gate, "gateId" | "status" | "evidence">>;
  p0Total: number;
  failed: number;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertStringField(obj: Record<string, unknown>, field: string, context: string): string {
  const value = obj[field];
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`missing required field: ${field} (${context})`);
  }
  return value;
}

function parseGateLevel(value: string, index: number): GateLevel {
  if (value === "P0" || value === "P1" || value === "P2") return value;
  throw new Error(`invalid gate level at gates[${index}].level: ${value}`);
}

function parseGateStatus(value: string, index: number): GateStatus {
  if (value === "pass" || value === "fail") return value;
  throw new Error(`invalid gate status at gates[${index}].status: ${value}`);
}

export function validateGateConfig(value: unknown): GateConfig {
  if (!isObject(value)) {
    throw new Error("invalid gate config: root must be an object");
  }

  const version = assertStringField(value, "version", "root");
  const rawGates = value["gates"];
  if (!Array.isArray(rawGates) || rawGates.length === 0) {
    throw new Error("missing required field: gates (root)");
  }

  const gates: Gate[] = rawGates.map((item, index) => {
    if (!isObject(item)) {
      throw new Error(`invalid gate at gates[${index}]: must be object`);
    }

    const gateId = assertStringField(item, "gateId", `gates[${index}]`);
    const level = parseGateLevel(assertStringField(item, "level", `gates[${index}]`), index);
    const command = assertStringField(item, "command", `gates[${index}]`);
    const status = parseGateStatus(assertStringField(item, "status", `gates[${index}]`), index);
    const evidence = assertStringField(item, "evidence", `gates[${index}]`);

    return { gateId, level, command, status, evidence };
  });

  return { version, gates };
}

export async function loadGateConfig(filePath: string): Promise<GateConfig> {
  const raw = await readFile(filePath, "utf8");
  let parsed: unknown;
  try {
    // YAML 1.2 is a superset of JSON, so we keep gate files JSON-shaped for deterministic parsing.
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(`invalid gate config: expected JSON-shaped YAML at ${filePath}`);
  }

  return validateGateConfig(parsed);
}

export function summarizeGateResults(config: GateConfig): GateSummary {
  const results = config.gates.map(({ gateId, status, evidence }) => ({ gateId, status, evidence }));
  const p0Total = config.gates.filter((gate) => gate.level === "P0").length;
  const failed = config.gates.filter((gate) => gate.level === "P0" && gate.status === "fail").length;
  return { results, p0Total, failed };
}

export function formatGateSummary(summary: GateSummary): string {
  const lines = summary.results.map(
    (result) => `gateId=${result.gateId} status=${result.status} evidence=${result.evidence}`,
  );
  lines.push(`P0_TOTAL=${summary.p0Total}`);
  lines.push(`FAILED=${summary.failed}`);
  return lines.join("\n");
}
