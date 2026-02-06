import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";

const DEFAULT_THRESHOLDS_MS = {
  routerMs: 30,
  ftsMs: 30,
  toolTimeoutMs: 1000,
  schedulerTickMs: 10,
};

function parseArgs(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      result[key] = "true";
      continue;
    }
    result[key] = next;
    i += 1;
  }
  return result;
}

function parseNonNegativeInt(value, fieldName, fallback) {
  if (value == null) return fallback;
  const num = Number.parseInt(value, 10);
  if (!Number.isFinite(num) || num < 0) {
    throw new Error(`invalid ${fieldName}: expected non-negative integer`);
  }
  return num;
}

function parseOptionalNumber(value) {
  if (value == null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  return value;
}

function parseFlakeItem(item, index) {
  if (typeof item === "boolean") return item;
  if (item && typeof item === "object" && typeof item.ok === "boolean") {
    return item.ok;
  }
  throw new Error(`invalid flake result at index ${index}: expected boolean or { ok: boolean }`);
}

async function loadJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

function evaluatePerformance(observedInput, thresholdsMs) {
  const observedMs = {};
  const exceeded = [];
  const missing = [];

  for (const metric of Object.keys(thresholdsMs)) {
    const observed = parseOptionalNumber(observedInput?.[metric]);
    observedMs[metric] = observed;
    if (observed == null) {
      missing.push(metric);
      continue;
    }
    if (observed > thresholdsMs[metric]) {
      exceeded.push(metric);
    }
  }

  return {
    observedMs,
    exceeded,
    missing,
    // Missing metrics means the SLO gate cannot be proven; treat as fail-closed.
    status: exceeded.length > 0 || missing.length > 0 ? "fail" : "pass",
  };
}

function runFlakeRounds(command, rounds) {
  const outcomes = [];
  for (let i = 0; i < rounds; i += 1) {
    const result = spawnSync(command, {
      shell: true,
      stdio: "inherit",
      env: process.env,
    });
    outcomes.push(result.status === 0);
  }
  return outcomes;
}

const args = parseArgs(process.argv.slice(2));
const thresholdsMs = {
  routerMs: parseNonNegativeInt(args["threshold-router-ms"], "threshold-router-ms", DEFAULT_THRESHOLDS_MS.routerMs),
  ftsMs: parseNonNegativeInt(args["threshold-fts-ms"], "threshold-fts-ms", DEFAULT_THRESHOLDS_MS.ftsMs),
  toolTimeoutMs: parseNonNegativeInt(
    args["threshold-tool-timeout-ms"],
    "threshold-tool-timeout-ms",
    DEFAULT_THRESHOLDS_MS.toolTimeoutMs,
  ),
  schedulerTickMs: parseNonNegativeInt(
    args["threshold-scheduler-tick-ms"],
    "threshold-scheduler-tick-ms",
    DEFAULT_THRESHOLDS_MS.schedulerTickMs,
  ),
};

let outcomes;
if (args["flake-results"]) {
  const input = await loadJson(args["flake-results"]);
  if (!Array.isArray(input) || input.length === 0) {
    throw new Error("invalid flake-results: expected non-empty array");
  }
  outcomes = input.map(parseFlakeItem);
} else {
  const rounds = parseNonNegativeInt(args.rounds, "rounds", 10);
  if (rounds === 0) {
    throw new Error("invalid rounds: expected at least 1");
  }
  const command = args["flake-command"] ?? "pnpm -C apps/desktop test:e2e";
  outcomes = runFlakeRounds(command, rounds);
}

const rounds = parseNonNegativeInt(args.rounds, "rounds", outcomes.length);
if (rounds !== outcomes.length) {
  throw new Error(`invalid rounds: expected ${outcomes.length} to match flake-results length`);
}

const maxFailures = parseNonNegativeInt(args["max-failures"], "max-failures", 0);
const failures = outcomes.filter((ok) => !ok).length;

const flake = {
  gateId: "P0.E2E_FLAKE",
  rounds,
  failures,
  maxFailures,
  exceeded: failures > maxFailures,
  status: failures > maxFailures ? "fail" : "pass",
  outcomes,
};

const observedInput = args["perf-observed"] ? await loadJson(args["perf-observed"]) : {};
const performanceResult = evaluatePerformance(observedInput, thresholdsMs);
const performance = {
  gateId: "P0.CORE_SLO",
  thresholdsMs,
  observedMs: performanceResult.observedMs,
  exceeded: performanceResult.exceeded,
  missing: performanceResult.missing,
  status: performanceResult.status,
};

const report = {
  schemaVersion: "bao.release-gate-checks/v1",
  generatedAt: new Date().toISOString(),
  flake,
  performance,
};

if (args.output) {
  await writeFile(args.output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
}

process.stdout.write(`${JSON.stringify(report)}\n`);

if (flake.status === "fail" || performance.status === "fail") {
  process.exitCode = 1;
}
