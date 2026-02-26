#!/bin/bash
# Count core agent lines (excluding channels/, cli/, providers/, skills/, and external coding tools)
cd "$(dirname "$0")" || exit 1

echo "bao core agent line count"
echo "================================"
echo ""

for dir in agent agent/tools bus config cron heartbeat session utils; do
  count=$(find "bao/$dir" -maxdepth 1 -name "*.py" ! -name "codex.py" ! -name "opencode.py" ! -name "claudecode.py" ! -name "coding_agent_base.py" ! -name "desktop.py" ! -name "image_gen.py" -exec cat {} + | wc -l)
  printf "  %-16s %5s lines\n" "$dir/" "$count"
done

root=$(cat bao/__init__.py bao/__main__.py | wc -l)
printf "  %-16s %5s lines\n" "(root)" "$root"

echo ""
total=$(find bao -name "*.py" ! -path "*/channels/*" ! -path "*/cli/*" ! -path "*/providers/*" ! -path "*/skills/*" ! -name "codex.py" ! -name "opencode.py" ! -name "claudecode.py" ! -name "coding_agent_base.py" ! -name "desktop.py" ! -name "image_gen.py" | xargs cat | wc -l)
echo "  Core total:     $total lines"
echo ""
echo "  (excludes: channels/, cli/, providers/, skills/, coding agents, desktop.py, image_gen.py)"
