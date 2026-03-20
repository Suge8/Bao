#!/bin/bash

set -euo pipefail

run_uv_pytest() {
    local mode="${1:-core}"
    local -a uv_args=(--extra dev)

    case "$mode" in
        core)
            ;;
        desktop)
            uv_args+=(--extra desktop)
            ;;
        *)
            echo "unknown uv pytest mode: $mode" >&2
            return 1
            ;;
    esac

    shift || true
    PYTHONPATH=. uv run "${uv_args[@]}" python -m pytest "$@"
}
