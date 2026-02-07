import path from "node:path";
import { access, mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import {
  loadGateConfigFromFile,
  resolveGateConfigPath,
  resolveScriptsRepoRoot,
} from "./release-gates-config.mjs";

const repoRoot = resolveScriptsRepoRoot(import.meta.url);

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function parseCliArgs(argv) {
  let configPathArg;
  let run = false;

  for (const token of argv) {
    if (token === "--run") {
      run = true;
      continue;
    }
    if (!token.startsWith("--") && configPathArg == null) {
      configPathArg = token;
      continue;
    }
    throw new Error(`unsupported argument: ${token}`);
  }

  return { configPathArg, run };
}

async function runGateAndWriteEvidence(gate, repoRoot) {
  const evidencePath = path.resolve(repoRoot, gate.evidence);
  const startedAt = new Date().toISOString();
  const result = spawnSync(gate.command, {
    shell: true,
    cwd: repoRoot,
    env: process.env,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  });

  const status = result.status === 0 ? "pass" : "fail";
  const payload = [
    `generatedAt=${startedAt}`,
    `gateId=${gate.gateId}`,
    `level=${gate.level}`,
    `command=${gate.command}`,
    `status=${status}`,
    `exitCode=${result.status ?? "null"}`,
    `signal=${result.signal ?? "none"}`,
    `spawnError=${result.error ? String(result.error.message ?? result.error) : "none"}`,
    "--- stdout ---",
    result.stdout ?? "",
    "--- stderr ---",
    result.stderr ?? "",
  ].join("\n");

  await mkdir(path.dirname(evidencePath), { recursive: true });
  await writeFile(evidencePath, `${payload}\n`, "utf8");

  return {
    status,
    evidenceExists: true,
  };
}

async function validateChecklist() {
  const { configPathArg, run } = parseCliArgs(process.argv.slice(2));
  const configPath = resolveGateConfigPath(configPathArg, repoRoot);

  let config;
  try {
    config = await loadGateConfigFromFile(configPath);
  } catch {
    console.error(`FAILED to read gate config: ${configPath}`);
    process.exit(1);
  }

  const p0Gates = config.gates.filter(g => g.level === "P0");
  const results = [];
  const missingEvidence = [];
  let failedGates = 0;

  for (const gate of p0Gates) {
    let status = gate.status;
    let exists = false;

    if (run) {
      try {
        const gateResult = await runGateAndWriteEvidence(gate, repoRoot);
        status = gateResult.status;
        exists = gateResult.evidenceExists;
      } catch {
        status = "fail";
        exists = false;
      }
    } else {
      const evidencePath = path.resolve(repoRoot, gate.evidence);
      exists = await fileExists(evidencePath);
    }

    const gateResult = {
      gateId: gate.gateId,
      status,
      evidence: gate.evidence,
      evidenceExists: exists
    };
    results.push(gateResult);

    if (status !== "pass") {
      failedGates++;
    }
    if (!exists) {
      missingEvidence.push(gate.evidence);
    }
  }

  const p0Total = results.length;
  const p0Pass = results.filter(r => r.status === "pass").length;
  const evidenceCheck = missingEvidence.length === 0 ? "pass" : "fail";
  const overall = (failedGates === 0 && evidenceCheck === "pass") ? "GO" : "NO-GO";

  const lines = [
    `CHECKLIST_VERSION=${config.version}`,
    `RUN_MODE=${run ? 1 : 0}`,
    `P0_TOTAL=${p0Total}`,
    `P0_PASS=${p0Pass}`,
    `FAILED_GATES=${failedGates}`,
    `EVIDENCE_CHECK=${evidenceCheck}`,
    `MISSING_EVIDENCE_COUNT=${missingEvidence.length}`,
    `OVERALL_RESULT=${overall}`
  ];

  results.forEach(r => {
    lines.push(`gateId=${r.gateId} status=${r.status} evidence=${r.evidence} exists=${r.evidenceExists ? 1 : 0}`);
  });

  if (missingEvidence.length > 0) {
    lines.push("MISSING_PATHS=" + missingEvidence.join(","));
  }

  process.stdout.write(lines.join("\n") + "\n");

  if (overall === "NO-GO") {
    process.exit(1);
  }
}

validateChecklist().catch(err => {
  console.error(err);
  process.exit(1);
});
