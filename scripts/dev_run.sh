#!/bin/bash
# scripts/dev_run.sh — 开发用自动重启包装器
#
# 用法: bash scripts/dev_run.sh [Bao 参数...]
#
# AI agent 改完代码后 kill 掉 Bao 进程即可触发重启。
# exit 0 = 正常退出不重启，其他退出码 = 自动重启。
# Ctrl+C = 停止整个包装器。
# 连续快速崩溃 5 次自动停止，防止死循环。

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

MAX_RAPID=5
RAPID_WINDOW=30
DELAY=2

rapid_count=0
last_start=0
BAO_PID=""

cleanup() {
    echo ""
    echo "[dev] 收到终止信号，正在关闭..."
    if [ -n "$BAO_PID" ] && kill -0 "$BAO_PID" 2>/dev/null; then
        kill "$BAO_PID" 2>/dev/null
        wait "$BAO_PID" 2>/dev/null
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

while true; do
    now=$(date +%s)

    # 崩溃循环检测
    if (( now - last_start < RAPID_WINDOW )); then
        (( rapid_count++ )) || true
        if (( rapid_count >= MAX_RAPID )); then
            echo "[dev] ${RAPID_WINDOW}s 内连续重启 ${rapid_count} 次，停止。"
            exit 1
        fi
    else
        rapid_count=0
    fi

    last_start=$now
    echo "[dev] 启动 Bao... ($(date '+%Y-%m-%d %H:%M:%S'))"

    uv run bao "$@" &
    BAO_PID=$!
    wait $BAO_PID 2>/dev/null
    CODE=$?
    BAO_PID=""

    if [ $CODE -eq 0 ]; then
        echo "[dev] Bao 正常退出，停止。"
        break
    fi

    echo "[dev] Bao 退出 (code=$CODE)，${DELAY}s 后重启..."
    sleep $DELAY
done
