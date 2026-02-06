import path from "node:path";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

function assertStringField(obj, field, context) {
  const value = obj[field];
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`missing required field: ${field} (${context})`);
  }
  return value;
}

function validateGateConfig(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("invalid gate config: root must be an object");
  }

  const version = assertStringField(value, "version", "root");
  const gates = value.gates;
  if (!Array.isArray(gates) || gates.length === 0) {
    throw new Error("missing required field: gates (root)");
  }

  return {
    version,
    gates: gates.map((gate, index) => {
      if (!gate || typeof gate !== "object" || Array.isArray(gate)) {
        throw new Error(`invalid gate at gates[${index}]: must be object`);
      }
      const level = assertStringField(gate, "level", `gates[${index}]`);
      const status = assertStringField(gate, "status", `gates[${index}]`);
      if (level !== "P0" && level !== "P1" && level !== "P2") {
        throw new Error(`invalid gate level at gates[${index}].level: ${level}`);
      }
      if (status !== "pass" && status !== "fail") {
        throw new Error(`invalid gate status at gates[${index}].status: ${status}`);
      }

      return {
        gateId: assertStringField(gate, "gateId", `gates[${index}]`),
        level,
        command: assertStringField(gate, "command", `gates[${index}]`),
        status,
        evidence: assertStringField(gate, "evidence", `gates[${index}]`),
      };
    }),
  };
}

function assertBooleanField(obj, field, context) {
  const value = obj[field];
  if (typeof value !== "boolean") {
    throw new Error(`missing required boolean field: ${field} (${context})`);
  }
  return value;
}

function assertNonNegativeNumberField(obj, field, context) {
  const value = obj[field];
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`missing required numeric field: ${field} (${context})`);
  }
  return value;
}

function parseMetricMap(value, field) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`missing required field: ${field} (report.${field})`);
  }
  const keys = Object.keys(value);
  if (keys.length === 0) {
    throw new Error(`missing required metric fields: ${field} (report.${field})`);
  }

  const out = {};
  for (const key of keys.sort()) {
    const item = value[key];
    if (!(typeof item === "number" && Number.isFinite(item) && item >= 0) && item !== null) {
      throw new Error(`invalid metric value: ${field}.${key}`);
    }
    out[key] = item;
  }
  return out;
}

function validateGateCheckReport(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("invalid report: root must be an object");
  }
  const schemaVersion = assertStringField(value, "schemaVersion", "report");

  const flake = value.flake;
  if (!flake || typeof flake !== "object" || Array.isArray(flake)) {
    throw new Error("missing required field: flake (report)");
  }

  const performance = value.performance;
  if (!performance || typeof performance !== "object" || Array.isArray(performance)) {
    throw new Error("missing required field: performance (report)");
  }

  return {
    schemaVersion,
    flake: {
      gateId: assertStringField(flake, "gateId", "report.flake"),
      rounds: assertNonNegativeNumberField(flake, "rounds", "report.flake"),
      failures: assertNonNegativeNumberField(flake, "failures", "report.flake"),
      maxFailures: assertNonNegativeNumberField(flake, "maxFailures", "report.flake"),
      exceeded: assertBooleanField(flake, "exceeded", "report.flake"),
      status: assertStringField(flake, "status", "report.flake"),
    },
    performance: {
      gateId: assertStringField(performance, "gateId", "report.performance"),
      thresholdsMs: parseMetricMap(performance.thresholdsMs, "thresholdsMs"),
      observedMs: parseMetricMap(performance.observedMs, "observedMs"),
      exceeded: Array.isArray(performance.exceeded)
        ? performance.exceeded.map((v, i) => {
            if (typeof v !== "string") throw new Error(`invalid exceeded metric at report.performance.exceeded[${i}]`);
            return v;
          })
        : [],
      missing: Array.isArray(performance.missing)
        ? performance.missing.map((v, i) => {
            if (typeof v !== "string") throw new Error(`invalid missing metric at report.performance.missing[${i}]`);
            return v;
          })
        : [],
      status: assertStringField(performance, "status", "report.performance"),
    },
  };
}

function metricLineKey(metric) {
  return metric.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
}

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..");
const configPath = process.argv[2]
  ? path.resolve(process.cwd(), process.argv[2])
  : path.join(repoRoot, ".sisyphus", "release-gates", "v1.0-macos.yaml");
const reportPath = process.argv[3] ? path.resolve(process.cwd(), process.argv[3]) : null;

const parsed = JSON.parse(await readFile(configPath, "utf8"));
const config = validateGateConfig(parsed);

const lines = config.gates.map(
  (gate) => `gateId=${gate.gateId} status=${gate.status} evidence=${gate.evidence}`,
);
const p0Total = config.gates.filter((gate) => gate.level === "P0").length;
const failed = config.gates.filter((gate) => gate.level === "P0" && gate.status === "fail").length;
lines.push(`P0_TOTAL=${p0Total}`);
lines.push(`FAILED=${failed}`);

if (reportPath) {
  const report = validateGateCheckReport(JSON.parse(await readFile(reportPath, "utf8")));
  lines.push(`CHECK_REPORT_SCHEMA=${report.schemaVersion}`);
  lines.push(`FLAKE_GATE_ID=${report.flake.gateId}`);
  lines.push(`FLAKE_ROUNDS=${report.flake.rounds}`);
  lines.push(`FLAKE_FAILURES=${report.flake.failures}`);
  lines.push(`FLAKE_MAX_FAILURES=${report.flake.maxFailures}`);
  lines.push(`FLAKE_EXCEEDED=${report.flake.exceeded ? 1 : 0}`);
  lines.push(`FLAKE_STATUS=${report.flake.status}`);

  lines.push(`PERF_GATE_ID=${report.performance.gateId}`);
  lines.push(`PERF_STATUS=${report.performance.status}`);
  lines.push(`PERF_EXCEEDED=${report.performance.exceeded.length > 0 ? report.performance.exceeded.join(",") : "none"}`);
  lines.push(`PERF_MISSING=${report.performance.missing.length > 0 ? report.performance.missing.join(",") : "none"}`);

  for (const metric of Object.keys(report.performance.thresholdsMs).sort()) {
    const key = metricLineKey(metric);
    const threshold = report.performance.thresholdsMs[metric];
    const observed = report.performance.observedMs[metric];
    lines.push(`PERF_${key}_THRESHOLD=${threshold}`);
    lines.push(`PERF_${key}_OBSERVED=${observed === null ? "na" : observed}`);
  }
}

process.stdout.write(`${lines.join("\n")}\n`);
