# bao Skills

This directory contains built-in skills that ship with bao. User skills live in `~/.bao/workspace/skills/` (auto-discovered, highest priority).

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

## Attribution

The skill format and metadata structure follow [OpenClaw](https://github.com/openclaw/openclaw) conventions to maintain compatibility with the ClawHub skill ecosystem.

## Built-in Skills

| Skill | Description |
|-------|-------------|
| `memory` | LanceDB-backed memory with auto-consolidation and experience learning |
| `github` | Interact with GitHub using the `gh` CLI |
| `weather` | Get weather info using wttr.in and Open-Meteo |
| `summarize` | Summarize URLs, files, and YouTube videos |
| `tmux` | Remote-control tmux sessions |
| `cron` | Schedule reminders and recurring tasks |
| `clawhub` | Search and install skills from ClawHub registry |
| `skill-creator` | Create new skills |
| `agent-browser` | Browser automation for web testing, form filling, screenshots |
| `copywriting` | Marketing copy and content writing |
| `docx` | Word document creation, reading, editing |
| `find-skills` | Discover and install skills |
| `pdf` | PDF reading, merging, splitting, OCR |
| `pptx` | PowerPoint presentation creation and editing |
| `xlsx` | Excel spreadsheet creation, editing, data cleaning |
| `opencode` | Production-ready coding copilot flow for OpenCode (plan, implement, verify, iterate) |
| `codex` | Production-ready coding copilot flow for Codex CLI (execute, continue, inspect details) |
| `claudecode` | Delegate coding tasks to Claude Code CLI with session continuity and structured output |

Note: All three coding agents (OpenCode, Codex, Claude Code) are available both as built-in tools in `bao/agent/tools/` and as skills with workflow guidance.
