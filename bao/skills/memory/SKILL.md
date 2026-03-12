---
name: memory
description: Use for memory recall, consolidation, preferences, or project context.
always: true
---

# Memory

## Structure

- Long-term memory is split into four categories: **preference**, **personal**, **project**, **general**.
- Long-term memory is stored as fact rows in LanceDB and exposed as category-level read models; consolidation writes per-category durable facts.
- Experience entries use a columnar schema (quality, uses, successes, category, outcome as dedicated columns).
- Experience ranking uses quality-based retention (quality 5 = 365 days, 1 = 14 days) with Laplace-smoothed confidence.
- High-quality, frequently reused experiences (quality ≥ 5, uses ≥ 3) are immune from cleanup unless deprecated.
- Old text-based schemas are auto-migrated on first load.
- Retrieval is query-aware: low-information turns can skip heavy recall.
- Recall is resolved once per turn and then injected into prompt sections, avoiding split memory-trigger paths.
- Query embeddings use a short TTL cache; memory recall itself still follows the current store state each turn.
- If a query has no useful tokens, relevant long-term-memory injection can return empty context (zero-injection path).

## Explicit Memory Tools

- **remember** — Save a fact to a specific memory category (default: general).
- **forget** — Remove memory content matching a keyword from a category.
- **update_memory** — Overwrite a specific category's memory with new content.

Use these tools when the user explicitly asks to remember, forget, or update something.

## How To Use It

- Save durable user facts (preferences, project constraints, relationships) to the appropriate category.
- Reuse recalled memory in responses, but avoid repeating irrelevant history.
- Let the system manage consolidation and cleanup; no manual file maintenance is required.
- Treat occasional no-memory injection on short/low-information turns as expected behavior, not a memory failure.

## Notes

- Prefer concise, high-signal memory updates over verbose logs.
- Keep behavior unchanged: this skill improves recall quality, not tool behavior.
