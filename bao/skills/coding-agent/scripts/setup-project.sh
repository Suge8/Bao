#!/usr/bin/env bash
# Setup opencode.json for non-interactive use with bao.
# Usage: setup-project.sh <project-dir> [--model provider/model]
set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <project-dir> [--model provider/model]"
  echo ""
  echo "Creates opencode.json with auto-approve permissions for bao integration."
  echo ""
  echo "Options:"
  echo "  --model    Set default model (e.g. anthropic/claude-sonnet-4-20250514)"
  echo "  --help     Show this help"
  exit "${1:-0}"
}

PROJECT_DIR=""
MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --help|-h) usage 0 ;;
    -*) echo "Unknown option: $1" >&2; usage 1 ;;
    *) PROJECT_DIR="$1"; shift ;;
  esac
done

if [[ -z "$PROJECT_DIR" ]]; then
  echo "Error: project directory is required" >&2
  usage 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Error: directory does not exist: $PROJECT_DIR" >&2
  exit 1
fi

CONFIG_FILE="$PROJECT_DIR/opencode.json"

if [[ -f "$CONFIG_FILE" ]]; then
  echo "opencode.json already exists at $CONFIG_FILE"
  echo "Skipping creation to avoid overwriting existing config."
  exit 0
fi

# Build config JSON
if [[ -n "$MODEL" ]]; then
  cat > "$CONFIG_FILE" << EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "model": "$MODEL",
  "permission": {
    "edit": "allow",
    "bash": "allow"
  }
}
EOF
else
  cat > "$CONFIG_FILE" << 'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "allow",
    "bash": "allow"
  }
}
EOF
fi

echo "Created $CONFIG_FILE"
