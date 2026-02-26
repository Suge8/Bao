---
name: opencode
description: "Delegate coding tasks to OpenCode, an AI coding agent. Use when the user asks to write code, refactor, debug, add features, fix bugs, run tests, or perform any programming task on a project. Supports multi-turn conversations for iterative development."
metadata: {"bao":{"emoji":"⌨️","requires":{"bins":["opencode"]},"install":[{"id":"npm","kind":"shell","command":"npm i -g opencode-ai@latest","bins":["opencode"],"label":"Install OpenCode (npm)"},{"id":"brew","kind":"brew","formula":"anomalyco/tap/opencode","bins":["opencode"],"label":"Install OpenCode (brew)"}]}}
---

# OpenCode Skill

Delegate programming tasks to [OpenCode](https://opencode.ai), an AI coding agent with file editing, shell execution, and LSP support. You call the `opencode` tool via JSON parameters. OpenCode runs `opencode run` under the hood and returns structured results.

## When to use

Trigger this skill when the user asks to:
- Write, refactor, debug, or fix code
- Add features, create modules, or scaffold components
- Run tests and fix failures
- Perform any multi-file code change across a project

Do NOT use when:
- The user asks a conceptual question about code (answer directly)
- A single file read suffices (use `read_file`)
- A single shell command is needed (use `exec`)
- The task has nothing to do with programming

## Tool parameters reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Task description sent to OpenCode. Be specific, reference files. |
| `project_path` | string | no | workspace | Project directory to operate on. |
| `session_id` | string | no | — | Explicit OpenCode session ID to continue. |
| `continue_session` | boolean | no | true | Auto-resume the previous session for this chat context. |
| `fork` | boolean | no | false | Fork from an existing session instead of continuing in-place. |
| `model` | string | no | — | Override model in `provider/model` format (e.g. `anthropic/claude-sonnet-4-20250514`). |
| `agent` | string | no | — | OpenCode agent to use (e.g. `build`, `plan`). |
| `timeout_seconds` | integer | no | 600 | Execution timeout. Range: 30..1800. |
| `response_format` | string | no | `hybrid` | Output format: `hybrid`, `json`, or `text`. |
| `max_retries` | integer | no | 1 | Retry attempts on transient failures. Range: 0..2. |
| `max_output_chars` | integer | no | 4000 | Max chars for stdout/stderr in the response. Range: 200..50000. |
| `include_details` | boolean | no | false | Include full stdout/stderr inline. When false, use `opencode_details` to fetch. |

## One-shot task

The simplest pattern: send a prompt, get a result.

```
Use opencode with:
- prompt: "Add input validation to the create_user endpoint in src/api/users.py"
- project_path: "/home/user/myproject"
```

OpenCode executes the task, edits files on disk, and returns a structured response with status, summary, and session ID.

## Multi-turn workflow

Sessions let you iterate on a task across multiple rounds. By default, `continue_session` is true, so the tool automatically resumes the last session for the current chat context.

OpenCode CLI equivalent for this behavior is `opencode run --continue`.

Round 1, initial task:

```
Use opencode with:
- prompt: "Implement JWT authentication for the REST API in src/api/"
- project_path: "/home/user/myproject"
```

Round 2, follow-up (session auto-continues):

```
Use opencode with:
- prompt: "Good, but switch to httpOnly cookies instead of localStorage for token storage"
- project_path: "/home/user/myproject"
```

To continue a specific session explicitly:

```
Use opencode with:
- prompt: "Now add refresh token rotation"
- session_id: "ses_abc123"
```

To branch off without affecting the original session:

```
Use opencode with:
- prompt: "Try a different approach: use composition instead of inheritance"
- session_id: "ses_abc123"
- fork: true
```

Always relay OpenCode's full response to the user. If OpenCode asks a clarifying question or proposes a plan, forward it and wait for the user's decision.

## Agent selection

OpenCode ships with multiple agents. Pick the right one:

**build** (default): Full access. Reads files, edits code, runs shell commands. Use for all implementation tasks.

```
Use opencode with:
- prompt: "Add error handling to all API endpoints in src/api/"
- project_path: "/home/user/myproject"
```

**plan**: Read-only analysis. No file changes, no shell commands. Use when the user wants a review, audit, or plan before committing to changes.

```
Use opencode with:
- prompt: "Review the authentication flow and suggest improvements"
- project_path: "/home/user/myproject"
- agent: "plan"
```

Rule of thumb: if the user says "review", "analyze", "suggest", or "plan", use `plan`. If they say "fix", "add", "refactor", or "implement", use `build` (or omit `agent` entirely).

## Reading detailed output

By default, `include_details` is false to save context budget. The response includes a summary and a `request_id`. When you need the full stdout/stderr (e.g. to diagnose a failure), use the companion tool:

### opencode_details parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `request_id` | string | no | — | Specific request to fetch details for |
| `session_id` | string | no | — | Fetch latest run for this session |
| `max_chars` | integer | no | 12000 | Max chars for stdout/stderr (200..50000) |
| `include_stderr` | boolean | no | true | Whether to include stderr content |
| `response_format` | string | no | hybrid | Return format: hybrid, json, or text |

```
Use opencode_details with:
- request_id: "abc123def456"
```

You can also look up details by session:

```
Use opencode_details with:
- session_id: "ses_abc123"
```

If neither is provided, `opencode_details` returns the most recent run for the current chat context.

## Project setup

Before first use on a project, configure `opencode.json` in the project root to auto-approve file edits and shell commands. Without this, OpenCode may hit permission prompts that block non-interactive execution.

Run the setup script:

```
{baseDir}/scripts/setup-project.sh /path/to/project
```

Or create `opencode.json` manually in the project root:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "allow",
    "bash": "allow"
  }
}
```

Security note: this grants OpenCode full edit and bash access within the project. For sensitive repos, set `"bash": "deny"` to restrict shell access.

## Backend command templates

OpenCode supports custom commands via a `--command` parameter (e.g. `/init`, `/review`, and plugin-registered commands). However, command output is unreliable in non-interactive mode because many commands expect a TUI session for rendering.

Prefer natural language prompts that achieve the same effect:

| Instead of | Use this prompt |
|------------|----------------|
| `--command /init` | "Initialize this project: create AGENTS.md and set up conventions" |
| `--command /review` | "Review the recent changes and provide feedback" |

Natural language prompts give OpenCode full context and produce reliable, parseable output.

## Git workflow

OpenCode can perform git operations through natural language prompts. Do NOT rely on slash commands like `/commit` in non-interactive mode.

```
Use opencode with:
- prompt: "Stage all changes and commit with message 'feat: add JWT auth'"
- project_path: "/home/user/myproject"
```

```
Use opencode with:
- prompt: "Create a new branch 'feature/auth', commit the changes, and push to origin"
- project_path: "/home/user/myproject"
```

```
Use opencode with:
- prompt: "Create a pull request for the current branch with a summary of all changes"
- project_path: "/home/user/myproject"
```

OpenCode has full shell access (when `opencode.json` permits), so any git operation expressible as a shell command works through a natural language prompt.

## Best practices for prompts

- **Be specific.** "Add input validation to the `create_user` endpoint in `src/api/users.py`" beats "fix the API".
- **Reference files.** Mention exact paths so OpenCode knows where to look.
- **State the goal.** "Refactor to reduce duplication between `parse_v1` and `parse_v2`" beats "clean up the code".
- **Provide context.** "The tests in `tests/test_auth.py` fail because the JWT secret changed. Update the test fixtures."
- **One task per call.** Break large tasks into focused steps for better results and easier review.
- **Use plan first for big changes.** Run with `agent: "plan"` to get a proposal, then follow up with `build` to execute.

## Error handling

| Error | Cause | Fix |
|-------|-------|-----|
| `missing_binary` | `opencode` not on PATH | Install: `npm i -g opencode-ai@latest` or `brew install anomalyco/tap/opencode` |
| `provider_not_configured` | No LLM provider set up | Run `opencode auth login` to configure a provider |
| `permission_prompt_blocked` | `opencode.json` missing or set to `"ask"` | Run `{baseDir}/scripts/setup-project.sh /path/to/project` |
| `timeout` | Task exceeded `timeout_seconds` | Split the task into smaller steps, or increase `timeout_seconds` |
| `execution_failed` | Generic failure | Use `opencode_details` with the `request_id` to inspect full stdout/stderr |

Transient failures (rate limits, network resets, temporary errors) are automatically retried up to `max_retries` times.

## Interaction pattern

Follow this flow when delegating coding work:

1. **Translate** the user's request into a clear, file-specific prompt for OpenCode.
2. **Call** the `opencode` tool with appropriate parameters. Set `project_path` if the user specified a directory.
3. **Relay** OpenCode's response to the user. Never silently discard output.
4. **If OpenCode asks a question** or proposes a plan, forward it to the user and wait.
5. **For follow-ups**, call `opencode` again. Session continuity is automatic (`continue_session` defaults to true).
6. **If a run fails**, check the summary. Use `opencode_details` for the full picture before retrying.
7. **For large tasks**, start with `agent: "plan"` to get a proposal, then switch to `build` for execution.
