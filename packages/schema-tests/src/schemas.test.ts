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

async function loadSchemas() {
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

  return { ajv, schemas };
}

async function listDimsumManifestFiles(): Promise<string[]> {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = path.resolve(here, "..", "..", "..");

  return fg(["dimsums/*/*/manifest.json"], {
    cwd: repoRoot,
    absolute: true,
    onlyFiles: true,
  });
}

function schemaId(id: string): string {
  return `https://bao.schema/${id}`;
}

describe("schemas", () => {
  it("all schemas under /schemas compile (draft 2020-12)", async () => {
    const { ajv, schemas } = await loadSchemas();

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

  it("dimsum manifests match dimsum manifest schema", async () => {
    const { ajv } = await loadSchemas();
    const manifestFiles = await listDimsumManifestFiles();

    expect(manifestFiles.length).toBeGreaterThan(0);

    const validate = ajv.getSchema(schemaId("bao.dimsum.manifest/v1"));
    expect(validate, "schema not found: bao.dimsum.manifest/v1").toBeTypeOf("function");

    for (const manifestPath of manifestFiles) {
      const manifest = await loadJson(manifestPath);
      const ok = validate!(manifest);
      if (!ok) {
        throw new Error(`invalid dimsum manifest (${manifestPath}): ${JSON.stringify(validate!.errors)}`);
      }
    }
  });

  it("pipeline hook contracts match schema examples", async () => {
    const { ajv } = await loadSchemas();

    const assertValid = (id: string, instance: unknown) => {
      const validate = ajv.getSchema(schemaId(id));
      expect(validate, `schema not found: ${id}`).toBeTypeOf("function");
      const ok = validate!(instance);
      if (!ok) {
        throw new Error(`${id} invalid: ${JSON.stringify(validate!.errors)}`);
      }
    };

    assertValid("bao.router.input/v1", {
      userInput: "请调用工具",
    });

    assertValid("bao.memory.inject_input/v1", {
      userInput: "总结之前会话",
      memoryQuery: "之前的关键结论",
    });

    assertValid("bao.memory.inject_output/v1", {
      injected: "memory.injected: 关键结论",
    });

    assertValid("bao.toolcall.result/v1", {
      ok: false,
      output: { stderr: "boom" },
      error: "exit code 1",
      attempt: 1,
      toolName: "shell.exec",
    });

    assertValid("bao.corrector.validation/v1", {
      ok: false,
      error: "tool execution failed",
    });

    assertValid("bao.corrector.retry_input/v1", {
      attempt: 1,
      maxAttempts: 2,
      toolOk: false,
      validationOk: false,
    });

    assertValid("bao.corrector.retry_output/v1", {
      shouldRetry: true,
      reason: "tool_failed",
    });

    assertValid("bao.memory.extract_input/v1", {
      sessionId: "default",
      userInput: "请记住我喜欢乌龙茶",
      assistantOutput: "好的，我已经记住了",
      toolName: "shell.exec",
      toolTriggered: true,
      toolOk: true,
      providerUsed: "openai",
    });

    assertValid("bao.memory.mutation_plan/v1", {
      planId: "plan_1",
      mutations: [
        {
          op: "UPSERT",
          idempotencyKey: "idem_1",
          memory: {
            namespace: "chat.user",
            kind: "fact",
            title: "偏好",
            content: "喜欢乌龙茶",
            status: "active",
          },
        },
      ],
    });

    assertValid("bao.provider.call_error/v1", {
      source: "runEngineTurn",
      stage: "provider.call",
      sessionId: "default",
      code: "ERR_PROVIDER_CALL",
      error: "provider run timeout",
      provider: "bao.bundled.provider.openai",
      model: "gpt-4.1-mini",
      attempt: 1,
    });

    assertValid("bao.provider.run.output/v1", {
      kind: "message",
      message: "hello",
    });

    assertValid("bao.provider.run.output/v1", {
      kind: "tool_call",
      toolCall: {
        id: "tc_1",
        name: "shell.exec",
        args: { command: "echo", args: ["ok"] },
        source: {
          provider: "bao.bundled.provider.openai",
          model: "gpt-4.1-mini",
        },
      },
    });

    assertValid("bao.provider.delta/v1", {
      kind: "text",
      text: "partial",
    });

    assertValid("bao.provider.delta/v1", {
      kind: "tool_call",
      toolCall: {
        id: "tc_delta_1",
        name: "shell.exec",
        args: { command: "echo", args: ["delta"] },
        source: {
          provider: "bao.bundled.provider.openai",
          model: "gpt-4.1-mini",
        },
      },
    });

    assertValid("bao.provider.delta/v1", {
      kind: "done",
    });

    assertValid("bao.corrector.validate_tool_result_error/v1", {
      source: "runEngineTurn",
      stage: "corrector.validate_tool_result",
      sessionId: "default",
      code: "ERR_CORRECTOR_VALIDATE_TOOL_RESULT",
      error: "validator unavailable",
      toolName: "shell.exec",
      attempt: 1,
    });

    assertValid("bao.corrector.decide_retry_error/v1", {
      source: "runEngineTurn",
      stage: "corrector.decide_retry",
      sessionId: "default",
      code: "ERR_CORRECTOR_DECIDE_RETRY",
      error: "retry checker unavailable",
      toolName: "shell.exec",
      attempt: 1,
    });

    assertValid("bao.memory.extract_error/v1", {
      source: "runEngineTurn",
      stage: "memory.extract.apply_plan",
      sessionId: "default",
      code: "ERR_MEMORY_EXTRACT_APPLY_PLAN",
      error: "apply mutation plan failed",
      planId: "plan_1",
      mutationCount: 1,
    });


    assertValid("bao.memory.inject_error/v1", {
      source: "runEngineTurn",
      stage: "memory.inject.search",
      sessionId: "default",
      code: "ERR_MEMORY_INJECT_SEARCH",
      error: "search index failed",
      memoryQuery: "偏好",
    });

    assertValid("bao.event/v1", {
      eventId: 1,
      ts: 1,
      type: "provider.call.error",
      payload: {
        source: "runEngineTurn",
        stage: "provider.call",
        sessionId: "default",
        code: "ERR_PROVIDER_CALL",
        error: "provider run timeout",
        provider: "bao.bundled.provider.openai",
        model: "gpt-4.1-mini",
        attempt: 1,
      },
    });

    assertValid("bao.event/v1", {
      eventId: 2,
      ts: 2,
      type: "engine.turn",
      payload: {
        sessionId: "default",
        output: "ok",
        matched: false,
        needsMemory: false,
        toolName: null,
        toolTriggered: false,
        toolOk: null,
        toolValidationOk: null,
        toolValidationError: null,
        toolRetryReason: null,
        toolAttempts: 0,
        providerUsed: "bao.bundled.provider.openai",
        memoryPlanId: "plan_1",
        memoryMutationCount: 1,
      },
    });


    assertValid("bao.event/v1", {
      eventId: 21,
      ts: 21,
      type: "engine.turn",
      payload: {
        sessionId: "default",
        output: "tool shell.exec 执行成功",
        matched: true,
        needsMemory: false,
        toolName: "shell.exec",
        toolTriggered: true,
        toolOk: true,
        toolValidationOk: true,
        toolValidationError: null,
        toolRetryReason: null,
        toolAttempts: 1,
        providerUsed: null,
        memoryPlanId: "plan_tool_1",
        memoryMutationCount: 1,
      },
    });

    assertValid("bao.event/v1", {
      eventId: 3,
      ts: 3,
      type: "memory.extract.error",
      payload: {
        source: "runEngineTurn",
        stage: "memory.extract.plan",
        sessionId: "default",
        code: "ERR_MEMORY_EXTRACT_PLAN",
        error: "extract failed",
        planId: null,
        mutationCount: 0,
      },
    });

    assertValid("bao.event/v1", {
      eventId: 4,
      ts: 4,
      type: "corrector.validate_tool_result.error",
      payload: {
        source: "runEngineTurn",
        stage: "corrector.validate_tool_result",
        sessionId: "default",
        code: "ERR_CORRECTOR_VALIDATE_TOOL_RESULT",
        error: "validator unavailable",
        toolName: "shell.exec",
        attempt: 1,
      },
    });


    assertValid("bao.event/v1", {
      eventId: 5,
      ts: 5,
      type: "memory.inject.error",
      payload: {
        source: "runEngineTurn",
        stage: "memory.inject.pipeline",
        sessionId: "default",
        code: "ERR_MEMORY_INJECT_PIPELINE",
        error: "memory inject failed",
        memoryQuery: null,
      },
    });

    const retryValidate = ajv.getSchema(schemaId("bao.corrector.retry_output/v1"));
    expect(retryValidate).toBeTypeOf("function");
    expect(retryValidate!({ shouldRetry: true })).toBe(false);

    const resultValidate = ajv.getSchema(schemaId("bao.toolcall.result/v1"));
    expect(resultValidate).toBeTypeOf("function");
    expect(resultValidate!({ output: {} })).toBe(false);

    const providerErrorValidate = ajv.getSchema(schemaId("bao.provider.call_error/v1"));
    expect(providerErrorValidate).toBeTypeOf("function");
    expect(
      providerErrorValidate!({
        source: "runEngineTurn",
        stage: "provider.call",
        sessionId: "default",
        code: "ERR_PROVIDER_CALL",
        error: "provider run timeout",
        provider: "bao.bundled.provider.openai",
        model: "gpt-4.1-mini",
        attempt: 0,
      }),
    ).toBe(false);

    const providerRunOutputValidate = ajv.getSchema(schemaId("bao.provider.run.output/v1"));
    expect(providerRunOutputValidate).toBeTypeOf("function");
    expect(
      providerRunOutputValidate!({
        kind: "tool_call",
      }),
    ).toBe(false);

    const providerDeltaValidate = ajv.getSchema(schemaId("bao.provider.delta/v1"));
    expect(providerDeltaValidate).toBeTypeOf("function");
    expect(
      providerDeltaValidate!({
        kind: "text",
      }),
    ).toBe(false);

    const eventValidate = ajv.getSchema(schemaId("bao.event/v1"));
    expect(eventValidate).toBeTypeOf("function");
    expect(
      eventValidate!({
        eventId: 10,
        ts: 10,
        type: "provider.call.error",
        payload: {
          source: "runEngineTurn",
          stage: "provider.call",
          sessionId: "default",
          code: "ERR_PROVIDER_CALL",
          error: "provider run timeout",
          model: "gpt-4.1-mini",
          attempt: 1,
        },
      }),
    ).toBe(false);

    expect(
      eventValidate!({
        eventId: 11,
        ts: 11,
        type: "engine.turn",
        payload: {
          output: "ok",
          matched: false,
          needsMemory: false,
          toolTriggered: false,
          toolAttempts: 0,
          memoryMutationCount: 0,
        },
      }),
    ).toBe(false);

    expect(
      eventValidate!({
        eventId: 12,
        ts: 12,
        type: "corrector.decide_retry.error",
        payload: {
          source: "runEngineTurn",
          stage: "corrector.decide_retry",
          sessionId: "default",
          code: "ERR_CORRECTOR_DECIDE_RETRY",
          error: "retry checker unavailable",
          attempt: 1,
        },
      }),
    ).toBe(false);

    expect(
      eventValidate!({
        eventId: 13,
        ts: 13,
        type: "memory.extract.error",
        payload: {
          source: "runEngineTurn",
          stage: "memory.extract.plan",
          sessionId: "default",
          code: "ERR_ENGINE_TURN",
          error: "extract failed",
          planId: null,
          mutationCount: 0,
        },
      }),
    ).toBe(false);


    expect(
      eventValidate!({
        eventId: 14,
        ts: 14,
        type: "memory.inject.error",
        payload: {
          source: "runEngineTurn",
          stage: "memory.inject.search",
          sessionId: "default",
          code: "ERR_PROVIDER_CALL",
          error: "inject failed",
        },
      }),
    ).toBe(false);
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
