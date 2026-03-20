#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
source scripts/uv_pytest.sh

shopt -s nullglob

SOFT_INTERRUPT_TESTS=(tests/test_soft_interrupt_*.py)
SUBAGENT_PROGRESS_TESTS=(tests/test_subagent_progress_*.py)

if [ "${#SOFT_INTERRUPT_TESTS[@]}" -eq 0 ] || [ "${#SUBAGENT_PROGRESS_TESTS[@]}" -eq 0 ]; then
    echo "high risk test inputs missing" >&2
    exit 1
fi

run_uv_pytest core -m "integration and slow" \
    "${SOFT_INTERRUPT_TESTS[@]}" \
    tests/test_tool_interrupt.py \
    "${SUBAGENT_PROGRESS_TESTS[@]}" \
    "$@"
