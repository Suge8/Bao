# Bao Skills

This directory contains built-in skills that ship with Bao. User skills live in `~/.bao/workspace/skills/` (auto-discovered, highest priority).

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

At runtime, `bao/agent/skills.py` builds a compact skill index where each entry includes exact `path`, `source`, and `available` attributes. `bao/agent/context.py` consumes that index and instructs the agent to read the matched skill via the exact `path` value.

## Attribution

The skill format and metadata structure follow [OpenClaw](https://github.com/openclaw/openclaw) conventions to maintain compatibility with the ClawHub skill ecosystem.

## Built-in Skills

| Skill | Description |
|-------|-------------|
| `memory` | Memory recall, consolidation, preferences, and project context |
| `github` | GitHub issues, PRs, Actions, releases, and repo queries |
| `weather` | Current weather, forecasts, and location-based weather questions |
| `summarize` | Summaries and transcript extraction for URLs, files, podcasts, and videos |
| `tmux` | Interactive terminal sessions, TUI apps, and long-lived CLI workflows |
| `cron` | Reminders, recurring tasks, and one-time scheduled jobs |
| `clawhub` | Find, install, or update skills from ClawHub |
| `skill-creator` | Create new skills |
| `agent-browser` | Browser automation, screenshots, form filling, web testing, and scraping |
| `copywriting` | Marketing copy, headlines, CTAs, and page rewrites |
| `docx` | Word docs, reports, memos, letters, contracts, and .docx editing |
| `find-skills` | Find, install, or recommend skills and new capabilities |
| `pdf` | PDF reading, scans, OCR, forms, extraction, merge, split |
| `pptx` | Slides, decks, presentations, and .pptx editing |
| `xlsx` | Spreadsheets, Excel, CSV/TSV cleanup, and table editing |
| `coding-agent` | General coding fallback when no more specific coding skill matches |
| `image-gen` | Draw or generate images, art, and illustrations via Gemini API |

Note: All three coding backends are available as built-in tools in `bao/agent/tools/` and unified into a single skill with workflow guidance.
