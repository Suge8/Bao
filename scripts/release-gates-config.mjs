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

function parseGateLevel(value, index) {
  if (value === "P0" || value === "P1" || value === "P2") {
    return value;
  }
  throw new Error(`invalid gate level at gates[${index}].level: ${value}`);
}

function parseGateStatus(value, index) {
  if (value === "pass" || value === "fail") {
    return value;
  }
  throw new Error(`invalid gate status at gates[${index}].status: ${value}`);
}

export function resolveScriptsRepoRoot(importMetaUrl) {
  const here = path.dirname(fileURLToPath(importMetaUrl));
  return path.resolve(here, "..");
}

export function resolveGateConfigPath(configPathArg, repoRoot) {
  if (configPathArg) {
    return path.resolve(process.cwd(), configPathArg);
  }
  return path.join(repoRoot, ".sisyphus", "release-gates", "v1.0-macos.yaml");
}

export function validateGateConfig(value) {
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

      const context = `gates[${index}]`;
      const level = parseGateLevel(assertStringField(gate, "level", context), index);
      const status = parseGateStatus(assertStringField(gate, "status", context), index);
      return {
        gateId: assertStringField(gate, "gateId", context),
        level,
        command: assertStringField(gate, "command", context),
        status,
        evidence: assertStringField(gate, "evidence", context),
      };
    }),
  };
}

export async function loadGateConfigFromFile(configPath) {
  const parsed = JSON.parse(await readFile(configPath, "utf8"));
  return validateGateConfig(parsed);
}
