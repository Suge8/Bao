#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

if [ "$#" -eq 0 ]; then
    echo "Usage: bash scripts/test_targeted.sh <pytest args...>"
    echo "Example: bash scripts/test_targeted.sh tests/test_chat_service.py -q"
    echo "Example: bash scripts/test_targeted.sh -k 'chat_service or gateway' -q"
    exit 1
fi

PYTHONPATH=. uv run pytest "$@"
