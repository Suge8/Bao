---
name: clawhub
description: Use to find, install, or update skills from ClawHub.
homepage: https://clawhub.ai
metadata: {"bao":{"emoji":"🦞"}}
---

# ClawHub

Public skill registry for AI agents. Search by natural language (vector search).

## When to use

Use this skill when the user asks any of:
- "find a skill for …"
- "search for skills"
- "install a skill"
- "what skills are available?"
- "update my skills"

## Search

```bash
npx --yes clawhub@latest search "web scraping" --limit 5
```

## Install

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.bao/workspace
```

Replace `<slug>` with the skill name from search results. This places the skill into `~/.bao/workspace/skills/`, where Bao loads workspace skills from. Always include `--workdir`.

## Update

```bash
npx --yes clawhub@latest update --all --workdir ~/.bao/workspace
```

## List installed

```bash
npx --yes clawhub@latest list --workdir ~/.bao/workspace
```

## Notes

- Requires Node.js (`npx` comes with it).
- No API key needed for search and install.
- Login (`npx --yes clawhub@latest login`) is only required for publishing.
- `--workdir ~/.bao/workspace` is critical — without it, skills install to the current directory instead of the Bao workspace.
- After install, remind the user to start a new session to load the skill.
