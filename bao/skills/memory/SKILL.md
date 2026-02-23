---
name: memory
description: LanceDB-backed memory with automatic recall and consolidation.
always: true
---

# Memory

## Structure

- Long-term memory and conversation history are persisted in LanceDB.
- Experience entries are stored and reused automatically for similar tasks.

## How To Use It

- Save durable user facts (preferences, project constraints, relationships) when they appear.
- Reuse recalled memory in responses, but avoid repeating irrelevant history.
- Let the system manage consolidation and cleanup; no manual file maintenance is required.

## Notes

- Prefer concise, high-signal memory updates over verbose logs.
- Keep behavior unchanged: this skill improves recall quality, not tool behavior.
