---
name: clawhub
description: Use to find, install, or update skills from ClawHub.
homepage: https://clawhub.ai
metadata: {"bao":{"emoji":"🦞","icon":"toolbox","display":{"name":"ClawHub Market","nameZh":"ClawHub 市场","descriptionZh":"查找、安装或更新外部技能。"},"category":"discovery","capabilityRefs":["exec"],"activationRefs":["exec"],"requires":{"bins":["npx"]},"examplePrompts":["帮我找一个适合做 PR review 的技能","从 ClawHub 安装一个前端设计技能"]}}
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

Replace `<slug>` with the skill name from search results. `--workdir ~/.bao/workspace` is still required for the install workflow, but Bao copies the selected skill into `~/.bao/skills/`, which is the runtime user-skills directory.

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
- `--workdir ~/.bao/workspace` is critical — without it, the staging install lands in the current directory instead of Bao's shared workspace.
- After install, remind the user to start a new session to load the skill.
