---
name: claudecode
description: "Delegate coding tasks to Claude Code CLI (`claude -p`). Use for implementing features, fixing bugs, refactoring code, and running iterative coding conversations with session continuity."
metadata: {"bao":{"emoji":"🤖","requires":{"bins":["claude"]},"install":[{"id":"npm","kind":"shell","command":"npm i -g @anthropic-ai/claude-code@latest","bins":["claude"],"label":"Install Claude Code (npm)"}]}}
---

# Claude Code Skill

Delegate programming tasks to Claude Code, Anthropic's official AI coding agent. Runs non-interactively via `claude -p`, returning structured JSON with session continuity.

## When to use

Use this skill when the user asks any of:
- "Write/modify/refactor/fix code in my project"
- "Add a feature to ..."
- "Debug this error ..."
- "Run the tests and fix failures"
- "Create a new module/component/file"
- Any task requiring reading, writing, or modifying source code

Do NOT use for:
- Simple questions about code concepts (answer directly)
- Reading a single file (use read_file tool)
- Running a one-off shell command (use exec tool)
- Tasks unrelated to coding

## Tools

- `claudecode`: Run coding tasks with session continuity, retries, and timeout protection
- `claudecode_details`: Fetch cached raw JSON stdout/stderr by `request_id` when details are omitted

## Tool parameters reference

### claudecode

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Task prompt sent to Claude Code |
| `project_path` | string | no | workspace | Project directory to operate in |
| `session_id` | string | no | — | Explicit Claude Code UUID session to continue |
| `continue_session` | boolean | no | true | Continue previous chat-specific session when available |
| `model` | string | no | — | Override model name for this run |
| `timeout_seconds` | integer | no | 600 | Execution timeout (30..1800 seconds) |
| `response_format` | string | no | "hybrid" | Return format: "hybrid", "json", or "text" |
| `max_retries` | integer | no | 1 | Retry attempts on transient failures (0..2) |
| `max_output_chars` | integer | no | 4000 | Max chars for stdout/stderr in output (200..50000) |
| `include_details` | boolean | no | false | Include full stdout/stderr in tool output |

### claudecode_details

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `request_id` | string | no | — | Specific request to fetch details for |
| `session_id` | string | no | — | Fetch latest run for this session |
| `max_chars` | integer | no | 12000 | Max chars for stdout/stderr (200..50000) |
| `include_stderr` | boolean | no | true | Whether to include stderr content |
| `response_format` | string | no | hybrid | Return format: hybrid, json, or text |

If neither `request_id` nor `session_id` is provided, returns the latest run for the current chat.

## One-shot task

For a standalone coding task, call `claudecode` with a clear prompt:

```
Use claudecode with:
- prompt: "Add input validation to the create_user endpoint in src/api/users.py"
```

The tool runs `claude -p`, parses the JSON output, and returns a summary with a `CLAUDECODE_META` block containing `request_id` and `session_id`.

## Multi-turn workflow

Claude Code tracks sessions via UUID. The tool auto-manages this per chat.

**Round 1, initial task:**

```
Use claudecode with:
- prompt: "Implement JWT authentication for the REST API in src/api/"
- continue_session: true
```

**Round 2+, follow-up in the same session:**

```
Use claudecode with:
- prompt: "Good, but use httpOnly cookies instead of localStorage"
- continue_session: true
```

When `continue_session` is true, the tool looks up the last session ID for this chat and passes `--resume <UUID>` to Claude Code. This preserves full conversation context across calls.

To explicitly target a specific session:

```
Use claudecode with:
- prompt: "Continue the refactoring from earlier"
- session_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

## Reading detailed output

By default, tool output is trimmed to `max_output_chars` (4000) to protect context budget. When you need the full picture:

**Option A, inline details:**

```
Use claudecode with:
- prompt: "Run the test suite and show all failures"
- include_details: true
- max_output_chars: 20000
```

**Option B, fetch after the fact:**

```
Use claudecode_details with:
- request_id: "req_abc123"
```

The details tool returns cached raw JSON stdout and stderr from the last run. No extra CLI call needed.

## Permission modes

Claude Code supports several permission modes for controlling what it can do:

| Mode | Behavior |
|------|----------|
| `default` | Asks for confirmation on risky operations |
| `acceptEdits` | Auto-approves file edits, asks for other operations |
| `plan` | Read-only analysis, no file changes |
| `dontAsk` | Auto-approves most operations |
| `bypassPermissions` | Skips all permission checks |

For non-interactive use (which is how bao calls it), `bypassPermissions` or `dontAsk` is recommended. The permission mode is configured in Claude Code's own settings, not passed as a tool parameter.

If you see permission-related errors, advise the user to configure their Claude Code permission mode:

```bash
# Set permission mode globally
claude config set --global permission_mode bypassPermissions
```

## Git workflow

Claude Code can handle git operations through natural language prompts:

```
Use claudecode with:
- prompt: "Create a new branch 'feat/user-auth', implement the changes, commit with a descriptive message"
- continue_session: true
```

```
Use claudecode with:
- prompt: "Review the staged changes, then create a PR with title 'Add user authentication' and a detailed description"
- continue_session: true
```

Claude Code has built-in git tools, so branch creation, commits, diffs, and PR creation all work through plain English prompts.

## Best practices

**Write specific prompts:**
- Good: "Add retry logic with exponential backoff to the HTTP client in `src/utils/http.py`, max 3 retries"
- Bad: "Fix the HTTP stuff"

**Reference files explicitly:**
- Good: "Refactor `src/api/handlers.py` to extract the validation logic into `src/api/validators.py`"
- Bad: "Refactor the handlers"

**Scope tasks tightly:**
- Break large features into focused steps
- One task per call produces better results than a sprawling multi-part prompt

**Use session continuity for iteration:**
- First call: implement the feature
- Second call: "Run the tests and fix any failures"
- Third call: "Add docstrings to the new functions"

**Set appropriate timeouts:**
- Quick edits: 120 seconds
- Feature implementation: 600 seconds (default)
- Large refactors or test suites: 900..1200 seconds

## Error handling

Common failure modes and fixes:

**Auth not configured:**
```
Error: authentication required
Fix: Run `claude auth login` in terminal
```

**Permission blocked:**
```
Error: permission denied for file edit
Fix: Configure permission mode — `claude config set --global permission_mode bypassPermissions`
```

**Timeout:**
```
Error: execution timed out after 600s
Fix: Increase timeout_seconds, or break the task into smaller pieces
```

**CLI not found:**
```
Error: claude binary not found
Fix: npm i -g @anthropic-ai/claude-code@latest
```

## Interaction pattern

When delegating coding work for the user:

1. **Translate** the user's request into a clear, specific prompt for Claude Code
2. **Call** `claudecode` with the prompt (use `continue_session: true` for follow-ups)
3. **Relay** Claude Code's response back to the user
4. **If details are needed**, call `claudecode_details` with the `request_id`
5. **If the user says "continue"** or gives feedback, pass it through in a new call with session continuity
6. **Never silently discard** output. The user needs to see what happened

## Limitations

- `claudecode` is blocking. The exec call waits until Claude Code finishes (may take several minutes for complex tasks)
- Claude Code requires its own API key/auth, separate from bao's provider configuration
- File changes are made directly on disk. Recommend using git so changes can be reviewed and reverted
- Session IDs are UUIDs managed by Claude Code. They persist across bao restarts but are tied to the Claude Code installation
