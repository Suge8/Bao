import path from "node:path";
import { readFile, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..");

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function validateChecklist() {
  const configPath = process.argv[2]
    ? path.resolve(process.cwd(), process.argv[2])
    : path.join(repoRoot, ".sisyphus", "release-gates", "v1.0-macos.yaml");

  let config;
  try {
    const content = await readFile(configPath, "utf8");
    config = JSON.parse(content);
  } catch (err) {
    console.error(`FAILED to read gate config: ${configPath}`);
    process.exit(1);
  }

  const p0Gates = config.gates.filter(g => g.level === "P0");
  const results = [];
  const missingEvidence = [];
  let failedGates = 0;

  for (const gate of p0Gates) {
    const evidencePath = path.resolve(repoRoot, gate.evidence);
    const exists = await fileExists(evidencePath);
    
    const gateResult = {
      gateId: gate.gateId,
      status: gate.status,
      evidence: gate.evidence,
      evidenceExists: exists
    };
    results.push(gateResult);

    if (gate.status !== "pass") {
      failedGates++;
    }
    if (!exists) {
      missingEvidence.push(gate.evidence);
    }
  }

  const p0Total = p0Gates.length;
  const p0Pass = p0Gates.filter(g => g.status === "pass").length;
  const evidenceCheck = missingEvidence.length === 0 ? "pass" : "fail";
  const overall = (failedGates === 0 && evidenceCheck === "pass") ? "GO" : "NO-GO";

  const lines = [
    `CHECKLIST_VERSION=${config.version}`,
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
