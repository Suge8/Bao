---
name: codex
description: "Delegate coding tasks to Codex CLI. Use for implementing features, fixing bugs, refactoring code, and running iterative coding conversations."
metadata: {"bao":{"emoji":"🧠","requires":{"bins":["codex"]}}}
---

# Codex Skill

Delegate coding work to Codex CLI through the `codex` tool. Codex runs non-interactively via `codex exec`, returning structured results with session tracking, retry logic, and output budget control.

## When to Use

Trigger `codex` when:
- The user asks to write, modify, or generate code
- A bug needs diagnosing and fixing
- Code needs refactoring, optimization, or migration
- Tests need writing or updating
- Git operations (commits, branches, merges) are requested via natural language
- A multi-step coding task benefits from iterative follow-ups in one session

Do NOT use `codex` when:
- The task is pure Q&A with no code changes needed
- A simple file read or directory listing suffices (use filesystem tools)
- The user explicitly asks to run a shell command (use shell tool)
- The task involves web browsing or search (use web tools)

## Tool Parameters Reference

### codex

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Task description sent to Codex. Be specific: name files, functions, expected behavior. |
| `project_path` | string | no | workspace | Project directory for Codex to operate in. |
| `session_id` | string | no | — | Explicit session ID to resume. Normally managed automatically per chat. |
| `continue_session` | boolean | no | true | Resume the previous session for this chat when one exists. |
| `model` | string | no | — | Override the default model (e.g. `o3-mini`, `o4-mini`). |
| `sandbox` | string | no | — | One of `read-only`, `workspace-write`, `danger-full-access`. |
| `full_auto` | boolean | no | false | Enable `--full-auto` for unattended execution without approval prompts. |
| `timeout_seconds` | integer | no | 600 | Execution timeout. Range: 30 to 1800 seconds. |
| `response_format` | string | no | hybrid | `hybrid` (summary + key output), `json` (raw structured), or `text` (plain). |
| `max_retries` | integer | no | 1 | Retry attempts on transient failures (overload, timeout, rate limit). Range: 0 to 2. |
| `max_output_chars` | integer | no | 4000 | Cap on stdout/stderr characters returned. Range: 200 to 50000. |
| `include_details` | boolean | no | false | Embed full stdout/stderr in the response. Leave false to save context budget. |

### codex_details

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `request_id` | string | no | — | Specific request to fetch details for |
| `session_id` | string | no | — | Fetch latest run for this session |
| `max_chars` | integer | no | 12000 | Max chars for stdout/stderr (200..50000) |
| `include_stderr` | boolean | no | true | Whether to include stderr content |
| `response_format` | string | no | hybrid | Return format: hybrid, json, or text |

If neither is provided, returns the latest run for the current chat automatically.

## One-Shot Task

For a standalone coding task, send a clear prompt with the right sandbox level:

```
Use codex with:
- prompt: "Add input validation to all POST endpoints in src/api/routes.py. Return 422 for missing required fields."
- sandbox: "workspace-write"
```

The response includes a summary, any key output, and a `CODEX_META` block with `request_id` and `session_id` for follow-up.

## Multi-Turn Workflow

Codex tracks sessions per chat. With `continue_session: true` (the default), follow-up calls automatically resume the same session, preserving file context and conversation history.

```
# First call — implement the feature
Use codex with:
- prompt: "Create a rate limiter middleware in src/middleware/rate_limit.py using a sliding window algorithm"
- sandbox: "workspace-write"

# Second call — iterate on it (session resumes automatically)
Use codex with:
- prompt: "Add unit tests for the rate limiter. Cover edge cases: burst traffic, window reset, concurrent requests."
- sandbox: "workspace-write"

# Third call — fix something from test output
Use codex with:
- prompt: "The concurrent request test is flaky. Use asyncio.Lock instead of threading.Lock."
```

To start fresh, set `continue_session: false`. To jump to a specific session, pass `session_id` explicitly.

## Sandbox Modes

Choose the minimum permission level needed:

- `read-only` — Codex can read files but not modify anything. Good for code review, analysis, and generating suggestions without side effects.
- `workspace-write` — Codex can read and write files within the project directory. The standard choice for most coding tasks.
- `danger-full-access` — Codex can execute arbitrary commands, install packages, modify system files. Only use when the task genuinely requires it (e.g. system configuration, package installation).

When no sandbox is specified, Codex uses its own default configuration. Always prefer `workspace-write` for typical code changes.

## Full-Auto Mode

Setting `full_auto: true` passes `--full-auto` to Codex, which skips all interactive approval prompts. This is useful for:
- Batch operations where you trust the task scope
- CI-like workflows that must run unattended
- Follow-up iterations where the approach is already validated

Without `full_auto`, Codex may block on permission prompts in non-interactive mode, causing the task to time out. If you see a `permission_blocked` error, either enable `full_auto` or adjust the Codex config profile.

```
Use codex with:
- prompt: "Refactor all database queries in src/db/ to use parameterized statements"
- sandbox: "workspace-write"
- full_auto: true
- timeout_seconds: 900
```

## Reading Detailed Output

By default, `include_details` is false to protect context budget. The response still contains a summary and key output. When you need the full picture (debugging failures, reviewing exact compiler errors), you have two options:

1. Set `include_details: true` on the original call (costs more context).
2. Call `codex_details` after the fact with the `request_id` from `CODEX_META`:

```
Use codex_details with:
- request_id: "abc-123-def"
```

The details tool pulls from an in-memory cache. It works as long as the agent process hasn't restarted since the original run.

## Code Review

Codex CLI ships a dedicated `codex review` command for code review workflows. This is a separate CLI command, not exposed through the `codex` tool. If the user asks for a code review, you can either:
- Use the `codex` tool with a review-oriented prompt and `read-only` sandbox
- Suggest the user run `codex review` directly in their terminal for the full interactive experience

## Git Workflow

Codex handles git operations through natural language. Pair with `workspace-write` or `danger-full-access` sandbox:

```
Use codex with:
- prompt: "Create a new branch 'feat/user-auth', implement JWT authentication in src/auth.py, commit with a descriptive message"
- sandbox: "workspace-write"
- full_auto: true
```

For operations that touch git config or push to remotes, use `danger-full-access`.

## Best Practices

1. Write specific prompts. Name exact files, functions, and expected behavior. Vague prompts produce vague results.
   - Good: "Add retry logic with exponential backoff to `fetch_data()` in `src/client.py`. Max 3 retries, starting at 1s delay."
   - Bad: "Add retry logic to the code."

2. Reference files by path. Codex works in the project directory but benefits from explicit paths.

3. Start with `read-only` for analysis, then switch to `workspace-write` for changes. Don't jump to `danger-full-access` unless necessary.

4. Keep `include_details: false` for routine tasks. Pull details only when debugging failures.

5. For large tasks, break them into focused steps across multiple calls in the same session. Each call builds on the previous context.

6. Set `timeout_seconds` proportional to task complexity. Simple edits: 120s. Multi-file refactors: 600s. Large migrations: 1200s+.

7. Use `max_output_chars` to control response size. Increase for tasks that produce verbose output (test runs, build logs). Decrease for simple edits.

## Error Handling

### Authentication (`auth_not_configured`)
Codex needs valid credentials. Tell the user to run:
```
codex login
```
Or for API key auth:
```
codex login --with-api-key
```

### Permission Blocked (`permission_blocked`)
Codex hit an approval prompt it couldn't answer non-interactively. Fix by:
- Enabling `full_auto: true`
- Adjusting the Codex config profile to pre-approve the operation type

### Timeout
The task exceeded `timeout_seconds`. Options:
- Increase the timeout for complex tasks
- Break the task into smaller steps
- Simplify the prompt to reduce scope

### Transient Failures
Rate limits, overloaded servers, connection resets. The tool retries automatically up to `max_retries` times. If it still fails, wait and try again.

## Interaction Pattern

The standard delegation flow:

1. Receive a coding request from the user.
2. Call `codex` with a specific prompt, appropriate sandbox, and `full_auto` if the task is well-scoped.
3. Read the summary from the response. Check `CODEX_META` for status.
4. Report results to the user. If something failed, pull details via `codex_details`.
5. For follow-ups, call `codex` again. The session continues automatically.
6. When the task is done, summarize what changed and where.

Keep the user informed at each step. Don't silently retry failed tasks without explaining what went wrong.
