#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

PYTHONPATH=. uv run pytest -m "integration and slow" \
    tests/test_soft_interrupt.py \
    tests/test_tool_interrupt.py \
    tests/test_subagent_progress.py \
    "$@"
