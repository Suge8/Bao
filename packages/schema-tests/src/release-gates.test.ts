import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
  formatGateSummary,
  loadGateConfig,
  summarizeGateResults,
  validateGateConfig,
  type GateConfig,
} from "./release-gates";

const execFileAsync = promisify(execFile);

const tempDirs: string[] = [];

async function createTempDir(): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "bao-release-gates-"));
  tempDirs.push(dir);
  return dir;
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("release gates", () => {
  it("fails fast when required gate fields are missing", () => {
    const invalid = {
      version: "v1.0-macos",
      gates: [{ gateId: "P0.TEST", level: "P0", command: "pnpm test", status: "pass" }],
    } as unknown;

    expect(() => validateGateConfig(invalid)).toThrowError(/missing required field: evidence/i);
  });

  it("loads v1.0 gate file and computes P0 totals", async () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const configPath = path.join(repoRoot, ".sisyphus", "release-gates", "v1.0-macos.yaml");
    const config = await loadGateConfig(configPath);
    const summary = summarizeGateResults(config);

    expect(summary.p0Total).toBeGreaterThan(0);
    expect(summary.failed).toBe(0);
    expect(summary.results.every((item: { gateId: string; status: string; evidence: string }) => item.gateId && item.status && item.evidence)).toBe(true);
  });

  it("formats machine-readable summary with gateId/status/evidence and P0 counters", async () => {
    const dir = await createTempDir();
    const file = path.join(dir, "gates.yaml");
    const fixture: GateConfig = {
      version: "v1.0-macos",
      gates: [
        {
          gateId: "P0.LINT",
          level: "P0",
          command: "pnpm lint",
          status: "pass",
          evidence: ".sisyphus/evidence/p0-lint.txt",
        },
        {
          gateId: "P0.TEST",
          level: "P0",
          command: "pnpm test",
          status: "fail",
          evidence: ".sisyphus/evidence/p0-test.txt",
        },
      ],
    };

    await writeFile(file, JSON.stringify(fixture, null, 2), "utf8");

    const loaded = await loadGateConfig(file);
    const output = formatGateSummary(summarizeGateResults(loaded));

    expect(output).toContain("gateId=P0.LINT status=pass evidence=.sisyphus/evidence/p0-lint.txt");
    expect(output).toContain("gateId=P0.TEST status=fail evidence=.sisyphus/evidence/p0-test.txt");
    expect(output).toContain("P0_TOTAL=2");
    expect(output).toContain("FAILED=1");
  });

  it("fails flake gate when repeated E2E failures exceed threshold and writes machine-readable report", async () => {
    const dir = await createTempDir();
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const scriptPath = path.join(repoRoot, "scripts", "release-gates-checks.mjs");
    const flakeResultsPath = path.join(dir, "flake-results.json");
    const perfObservedPath = path.join(dir, "perf-observed.json");
    const outputPath = path.join(dir, "gate-check-report.json");

    await writeFile(flakeResultsPath, JSON.stringify([true, false, true], null, 2), "utf8");
    await writeFile(
      perfObservedPath,
      JSON.stringify(
        {
          routerMs: 10,
          ftsMs: 10,
          toolTimeoutMs: 500,
          schedulerTickMs: 5,
        },
        null,
        2,
      ),
      "utf8",
    );

    await expect(
      execFileAsync("node", [
        scriptPath,
        "--flake-results",
        flakeResultsPath,
        "--perf-observed",
        perfObservedPath,
        "--rounds",
        "3",
        "--max-failures",
        "0",
        "--output",
        outputPath,
      ]),
    ).rejects.toMatchObject({
      code: 1,
    });

    const report = JSON.parse(await loadGateConfigAsText(outputPath));
    expect(report.flake.rounds).toBe(3);
    expect(report.flake.failures).toBe(1);
    expect(report.flake.maxFailures).toBe(0);
    expect(report.flake.exceeded).toBe(true);
    expect(report.flake.status).toBe("fail");
  });

  it("fails performance gate when core SLO threshold is exceeded", async () => {
    const dir = await createTempDir();
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const scriptPath = path.join(repoRoot, "scripts", "release-gates-checks.mjs");
    const flakeResultsPath = path.join(dir, "flake-results.json");
    const perfObservedPath = path.join(dir, "perf-observed.json");
    const outputPath = path.join(dir, "gate-check-report.json");

    await writeFile(flakeResultsPath, JSON.stringify([true, true], null, 2), "utf8");
    await writeFile(
      perfObservedPath,
      JSON.stringify(
        {
          routerMs: 31,
          ftsMs: 10,
          toolTimeoutMs: 500,
          schedulerTickMs: 5,
        },
        null,
        2,
      ),
      "utf8",
    );

    await expect(
      execFileAsync("node", [
        scriptPath,
        "--flake-results",
        flakeResultsPath,
        "--perf-observed",
        perfObservedPath,
        "--rounds",
        "2",
        "--max-failures",
        "0",
        "--threshold-router-ms",
        "30",
        "--output",
        outputPath,
      ]),
    ).rejects.toMatchObject({
      code: 1,
    });

    const report = JSON.parse(await loadGateConfigAsText(outputPath));
    expect(report.performance.exceeded).toContain("routerMs");
    expect(report.performance.status).toBe("fail");
  });

  it("fails performance gate when required SLO metrics are missing", async () => {
    const dir = await createTempDir();
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const scriptPath = path.join(repoRoot, "scripts", "release-gates-checks.mjs");
    const flakeResultsPath = path.join(dir, "flake-results.json");
    const perfObservedPath = path.join(dir, "perf-observed.json");
    const outputPath = path.join(dir, "gate-check-report.json");

    await writeFile(flakeResultsPath, JSON.stringify([true, true], null, 2), "utf8");
    await writeFile(
      perfObservedPath,
      JSON.stringify(
        {
          routerMs: 12,
          // Intentionally omit ftsMs/toolTimeoutMs/schedulerTickMs.
        },
        null,
        2,
      ),
      "utf8",
    );

    await expect(
      execFileAsync("node", [
        scriptPath,
        "--flake-results",
        flakeResultsPath,
        "--perf-observed",
        perfObservedPath,
        "--rounds",
        "2",
        "--max-failures",
        "0",
        "--output",
        outputPath,
      ]),
    ).rejects.toMatchObject({
      code: 1,
    });

    const report = JSON.parse(await loadGateConfigAsText(outputPath));
    expect(report.performance.missing).toContain("ftsMs");
    expect(report.performance.missing).toContain("toolTimeoutMs");
    expect(report.performance.missing).toContain("schedulerTickMs");
    expect(report.performance.status).toBe("fail");
  });

  it("includes flake/perf report fields in release-gate summary output", async () => {
    const dir = await createTempDir();
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const summaryScriptPath = path.join(repoRoot, "scripts", "release-gates-summary.mjs");
    const gateConfigPath = path.join(dir, "gates.yaml");
    const reportPath = path.join(dir, "gate-check-report.json");

    const fixture: GateConfig = {
      version: "v1.0-macos",
      gates: [
        {
          gateId: "P0.LINT",
          level: "P0",
          command: "pnpm lint",
          status: "pass",
          evidence: ".sisyphus/evidence/p0-lint.txt",
        },
      ],
    };
    await writeFile(gateConfigPath, JSON.stringify(fixture, null, 2), "utf8");
    await writeFile(
      reportPath,
      JSON.stringify(
        {
          schemaVersion: "bao.release-gate-checks/v1",
          generatedAt: "2026-02-07T00:00:00.000Z",
          flake: {
            gateId: "P0.E2E_FLAKE",
            rounds: 10,
            failures: 0,
            maxFailures: 0,
            exceeded: false,
            status: "pass",
          },
          performance: {
            gateId: "P0.CORE_SLO",
            thresholdsMs: {
              routerMs: 30,
              ftsMs: 30,
              toolTimeoutMs: 1000,
              schedulerTickMs: 10,
            },
            observedMs: {
              routerMs: 9,
              ftsMs: 8,
              toolTimeoutMs: 500,
              schedulerTickMs: 4,
            },
            exceeded: [],
            missing: [],
            status: "pass",
          },
        },
        null,
        2,
      ),
      "utf8",
    );

    const { stdout } = await execFileAsync("node", [summaryScriptPath, gateConfigPath, reportPath]);
    expect(stdout).toContain("FLAKE_ROUNDS=10");
    expect(stdout).toContain("FLAKE_FAILURES=0");
    expect(stdout).toContain("FLAKE_MAX_FAILURES=0");
    expect(stdout).toContain("PERF_ROUTERMS_THRESHOLD=30");
    expect(stdout).toContain("PERF_ROUTERMS_OBSERVED=9");
    expect(stdout).toContain("PERF_EXCEEDED=none");
  });

  describe("release-checklist-validate script", () => {
    it("fails with NO-GO and non-zero exit when P0 evidence is missing", async () => {
      const dir = await createTempDir();
      const here = path.dirname(fileURLToPath(import.meta.url));
      const repoRoot = path.resolve(here, "..", "..", "..");
      const scriptPath = path.join(repoRoot, "scripts", "release-checklist-validate.mjs");
      const gateConfigPath = path.join(dir, "gates.yaml");

      const fixture: GateConfig = {
        version: "v1.0-test",
        gates: [
          {
            gateId: "P0.MISSING",
            level: "P0",
            command: "echo test",
            status: "pass",
            evidence: ".sisyphus/evidence/non-existent.txt",
          },
        ],
      };
      await writeFile(gateConfigPath, JSON.stringify(fixture, null, 2), "utf8");

      await expect(execFileAsync("node", [scriptPath, gateConfigPath])).rejects.toMatchObject({
        code: 1,
        stdout: expect.stringContaining("OVERALL_RESULT=NO-GO"),
      });
    });

    it("succeeds with GO when all P0 gates pass and evidence files exist", async () => {
      const dir = await createTempDir();
      const here = path.dirname(fileURLToPath(import.meta.url));
      const repoRoot = path.resolve(here, "..", "..", "..");
      const scriptPath = path.join(repoRoot, "scripts", "release-checklist-validate.mjs");
      const gateConfigPath = path.join(dir, "gates.yaml");
      
      const evidenceSubPath = path.join(dir, "p0-success.txt");
      await writeFile(evidenceSubPath, "success", "utf8");
      
      const fixture: GateConfig = {
        version: "v1.0-test-go",
        gates: [
          {
            gateId: "P0.SUCCESS",
            level: "P0",
            command: "echo test",
            status: "pass",
            evidence: path.relative(repoRoot, evidenceSubPath),
          },
        ],
      };
      await writeFile(gateConfigPath, JSON.stringify(fixture, null, 2), "utf8");

      const { stdout } = await execFileAsync("node", [scriptPath, gateConfigPath]);
      expect(stdout).toContain("OVERALL_RESULT=GO");
      expect(stdout).toContain("EVIDENCE_CHECK=pass");
      expect(stdout).toContain("FAILED_GATES=0");
    });
  });
});

async function loadGateConfigAsText(filePath: string): Promise<string> {
  const { readFile } = await import("node:fs/promises");
  return readFile(filePath, "utf8");
}
