---
name: coding-agent
description: Use for general coding tasks when no more specific coding skill matches.
metadata: {"bao":{"emoji":"⌨️","requires":{"bins_any":["opencode","codex","claude"]}}}
---

# Coding Agent Skill

Delegate programming tasks to AI coding agents through the unified `coding_agent` tool. The tool routes to whichever backend is installed: OpenCode (`opencode`), Codex (`codex`), or Claude Code (`claudecode`). All backends share the same parameter interface, with a few backend-specific extras. Session continuity is backend-scoped: each backend keeps its own per-chat session chain.

## When to Use

Use `coding_agent` when the user asks to:
- Write, refactor, debug, or fix code
- Add features, create modules, scaffold components
- Run tests and fix failures
- Perform multi-file code changes across a project
- Git operations (commits, branches, PRs) via natural language

Do NOT use when:
- The user asks a conceptual question about code (answer directly)
- A single file read suffices (use `read_file`)
- A single shell command is needed (use `exec`)
- The task has nothing to do with programming

## Tool Parameters

### coding_agent

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent` | string | yes | — | Backend: `"opencode"`, `"codex"`, or `"claudecode"` |
| `prompt` | string | yes | — | Task description. Be specific, reference files. |
| `project_path` | string | no | workspace | Project directory to operate in. |
| `session_id` | string | no | — | Explicit session ID to continue. |
| `continue_session` | boolean | no | true | Auto-resume the previous session for this chat on the selected backend. |
| `model` | string | no | — | Override model (e.g. `anthropic/claude-sonnet-4-20250514`, `o4-mini`). |
| `timeout_seconds` | integer | no | 1800 | Optional execution timeout. Usually omit this and use the 30-minute default. Range: 30–1800. |
| `response_format` | string | no | `hybrid` | Output format: `hybrid`, `json`, or `text`. |
| `max_retries` | integer | no | 1 | Retry attempts on transient failures. Range: 0–2. |
| `max_output_chars` | integer | no | 4000 | Max chars for stdout/stderr. Range: 200–50000. |
| `include_details` | boolean | no | false | Include full stdout/stderr inline. |

**Backend-specific parameters** (ignored if wrong backend):

| Parameter | Backend | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `opencode_agent` | opencode | string | — | Agent type: `build` (default, full access) or `plan` (read-only analysis). Ignored unless `agent="opencode"`. |
| `fork` | opencode | boolean | false | Fork from existing session instead of continuing in-place. Ignored unless `agent="opencode"`. |
| `sandbox` | codex | string | — | `read-only`, `workspace-write`, or `danger-full-access`. Ignored unless `agent="codex"`. |
| `full_auto` | codex | boolean | false | Skip approval prompts for unattended execution. Ignored unless `agent="codex"`. |

### coding_agent_details

Fetch cached stdout/stderr from a previous run.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `request_id` | string | no | — | Specific request to fetch details for. |
| `session_id` | string | no | — | Fetch latest run for this session. |
| `agent` | string | no | — | Backend filter for `session_id` lookup: `opencode`, `codex`, `claudecode`. |
| `max_chars` | integer | no | 12000 | Max chars (200–50000). |
| `include_stderr` | boolean | no | true | Include stderr content. |
| `response_format` | string | no | hybrid | Return format. |

If neither is provided, returns the latest run for the current chat.

If only `session_id` is provided and multiple backends match, the tool returns an ambiguity error; pass `agent` to disambiguate.

## One-Shot Task

```
Use coding_agent with:
- agent: "opencode"
- prompt: "Add input validation to the create_user endpoint in src/api/users.py"
- project_path: "/home/user/myproject"
```

## Multi-Turn Workflow

Sessions persist per chat per backend. With `continue_session: true` (the default), follow-ups automatically resume the same backend session.

Session cache is in-memory, isolated per backend, and capped at 256 chat contexts per backend with least-recently-used eviction.

```
# Round 1 — implement
Use coding_agent with:
- agent: "opencode"
- prompt: "Implement JWT authentication for the REST API in src/api/"

# Round 2 — iterate (session auto-continues)
Use coding_agent with:
- agent: "opencode"
- prompt: "Switch to httpOnly cookies instead of localStorage for token storage"
```

To target a specific session explicitly, pass `session_id`. To branch off without affecting the original, pass `fork: true` (opencode only).

**Session discipline**: ALWAYS pass `continue_session: true` when following up on the same backend. This preserves context and avoids redundant file reads.

## Backend-Specific Features

### OpenCode

**Agent selection**: Use `opencode_agent: "plan"` for read-only analysis (review, audit, suggest). Omit or use `"build"` for implementation tasks. For oh-my-opencode custom agents, Bao accepts short names such as `Hephaestus` and resolves them to the current OpenCode display name when that short name is unique.

**Project setup**: Before first use, configure `opencode.json` in the project root for non-interactive execution:

```
{baseDir}/scripts/setup-project.sh /path/to/project
```

Or create `opencode.json` manually:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": { "edit": "allow", "bash": "allow" }
}
```

### Codex

**Sandbox modes**: Choose minimum permission needed:
- `read-only` — analysis only, no file changes
- `workspace-write` — read/write within project (standard choice)
- `danger-full-access` — arbitrary commands, system modifications

**Full-auto mode**: `full_auto: true` skips approval prompts. Use for well-scoped tasks and CI-like workflows. Without it, Codex may block on permission prompts causing timeouts.

**Code review**: `codex review` is a separate CLI command not exposed through the tool. For code review, use `coding_agent` with a review-oriented prompt and `read-only` sandbox.

### Claude Code

**Permission modes**: Configured in Claude Code settings, not via tool parameters:
- `default` — confirms risky operations
- `acceptEdits` — auto-approves edits
- `plan` — read-only
- `dontAsk` / `bypassPermissions` — auto-approves most/all operations

For non-interactive use, `bypassPermissions` or `dontAsk` is recommended:
```bash
claude config set --global permission_mode bypassPermissions
```

**Sessions**: Claude Code uses UUIDs. The tool auto-manages them per chat.

## Best Practices

1. **Be specific.** Name exact files, functions, and expected behavior.
2. **Reference files by path.** Explicit paths help the agent find the right code.
3. **One task per call.** Focused steps produce better results.
4. **Plan before big changes.** Use `opencode_agent: "plan"` or a review prompt first.
5. **Prefer the default timeout.** Usually omit `timeout_seconds` and use the 30-minute default. Only set it when the user explicitly asks for a non-default limit.
6. **Keep `include_details: false`** for routine tasks. Pull details only when debugging.

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `missing_binary` | CLI not on PATH | Install the required CLI (see below) |
| `auth_not_configured` | No LLM provider/API key | Run auth setup for the specific backend |
| `permission_prompt_blocked` | Permission config missing | Configure project permissions (see backend sections) |
| `timeout` | Exceeded `timeout_seconds` | Split the task, or adjust `timeout_seconds` when the user explicitly asks for a non-default limit (range: 30–1800s). |
| `execution_failed` | Generic failure | Use `coding_agent_details` to inspect full output |

**Installation commands:**
- OpenCode: `npm i -g opencode-ai@latest` or `brew install anomalyco/tap/opencode`
- Codex: `npm i -g @openai/codex@latest`
- Claude Code: `npm i -g @anthropic-ai/claude-code@latest`

**Auth setup:**
- OpenCode: `opencode auth login`
- Codex: `codex login` or `codex login --with-api-key`
- Claude Code: `claude auth login`

## Interaction Pattern

1. **Translate** the user's request into a clear, file-specific prompt.
2. **Call** `coding_agent` with the appropriate backend and parameters.
3. **Relay** the response to the user. Never silently discard output.
4. **If agent asks a question** or proposes a plan, forward it to the user.
5. **For follow-ups on the same backend**, call again with `continue_session: true`.
6. **If a run fails**, use `coding_agent_details` for diagnostics before retrying.
