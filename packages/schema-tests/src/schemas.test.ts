import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fg from "fast-glob";
import Ajv2020 from "ajv/dist/2020";
import { describe, expect, it } from "vitest";

type Json = Record<string, unknown>;

function deepClone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function rewriteBaoSchemaIds(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(rewriteBaoSchemaIds);
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      if ((k === "$id" || k === "$ref") && typeof v === "string" && v.startsWith("bao.")) {
        // Ajv expects URI-like identifiers. Keep the original ids on disk unchanged,
        // but validate by rewriting them into stable URL-based ids in-memory.
        out[k] = `https://bao.schema/${v}`;
        continue;
      }
      out[k] = rewriteBaoSchemaIds(v);
    }
    return out;
  }
  return value;
}

async function loadJson(filePath: string): Promise<Json> {
  const raw = await readFile(filePath, "utf8");
  return JSON.parse(raw) as Json;
}

describe("schemas", () => {
  it("all schemas under /schemas compile (draft 2020-12)", async () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const schemasDir = path.join(repoRoot, "schemas");

    const files = await fg(["**/*.schema.json"], {
      cwd: schemasDir,
      absolute: true,
      onlyFiles: true,
    });

    expect(files.length).toBeGreaterThan(0);

    const ajv = new Ajv2020({
      allErrors: true,
      strict: true,
      strictSchema: true,
      strictRequired: false,
      allowUnionTypes: true,
    });

    const rawSchemas = await Promise.all(files.map(loadJson));
    const schemas = rawSchemas.map((s) => rewriteBaoSchemaIds(deepClone(s)) as Json);

    for (const schema of schemas) {
      ajv.addSchema(schema);
    }

    // Validate each schema object itself.
    for (const schema of schemas) {
      const ok = ajv.validateSchema(schema);
      if (!ok) {
        throw new Error(JSON.stringify(ajv.errors, null, 2));
      }
    }

    // Compile each schema to ensure all refs resolve.
    for (const schema of schemas) ajv.compile(schema);
  });

  it("permissions_v1.json is well-formed", async () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "..", "..", "..");
    const p = path.join(repoRoot, "schemas", "permissions_v1.json");

    const json = await loadJson(p);
    expect(json["version"]).toBe("permissions/v1");
    expect(Array.isArray(json["capabilities"])).toBe(true);
    expect((json["capabilities"] as unknown[]).length).toBeGreaterThan(0);
  });
});
