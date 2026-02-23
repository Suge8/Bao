# bao Skills

This directory contains built-in skills that extend bao's capabilities.

bao is a lightweight AI assistant framework with enhanced agent intelligence (Thinking Protocol, Retry/Reflection, ExperienceLoop).

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

## Attribution

The skill format and metadata structure follow [OpenClaw](https://github.com/openclaw/openclaw) conventions to maintain compatibility with the ClawHub skill ecosystem.

## Available Skills

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