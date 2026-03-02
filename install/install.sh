#!/usr/bin/env bash

set -euo pipefail

readonly UV_INSTALL_URL="https://astral.sh/uv/install.sh"
readonly MIN_PYTHON="3.11"

info() {
  printf '[INFO] %s\n' "$1"
}

success() {
  printf '[OK] %s\n' "$1"
}

fail() {
  printf '[ERROR] %s\n' "$1" >&2
  exit 1
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "🖥️ 仅支持 macOS / macOS only"
  fi
}

ensure_uv() {
  if has_cmd uv; then
    success "✅ uv 已就绪 / uv is ready"
    return
  fi

  has_cmd curl || fail "❌ 缺少 curl，无法继续 / curl is required"
  info "📦 正在安装 uv / Installing uv"
  curl -LsSf "$UV_INSTALL_URL" | sh || fail "❌ uv 安装失败 / Failed to install uv"

  export PATH="$HOME/.local/bin:$PATH"
  has_cmd uv || fail "❌ 已安装但未找到 uv，请检查 PATH / uv not found in PATH"
  success "✅ uv 安装完成 / uv installed"
}

ensure_python() {
  info "🐍 准备 Python ${MIN_PYTHON} / Installing Python ${MIN_PYTHON}"
  uv python install "$MIN_PYTHON" || fail "❌ Python 安装失败 / Failed to install Python ${MIN_PYTHON}"
  success "✅ Python 已就绪 / Python is ready"
}

install_bao() {
  info "🚀 正在安装 bao-ai / Installing bao-ai from PyPI"
  uv tool install --upgrade bao-ai || fail "❌ bao-ai 安装失败 / Failed to install bao-ai"

  info "🔎 正在验证安装 / Verifying installation"
  uvx --from bao-ai bao --version >/dev/null || fail "❌ bao 命令验证失败 / Failed to verify bao"
  success "✅ bao-ai 安装成功 / bao-ai installed"
}

print_finish() {
  printf '\n'
  success "🎉 全部完成 / All done."
  info "👉 现在运行 bao 即可使用 / Run 'bao' to start"
  if ! has_cmd bao; then
    info "🛠️ 若找不到 bao，请加入 PATH / If 'bao' is not found, add PATH:"
    info "export PATH=\"$HOME/.local/bin:\$PATH\""
  fi
}

main() {
  info "🍞 Bao 一键安装（macOS）/ Bao one-click installer (macOS)"
  ensure_macos
  ensure_uv
  ensure_python
  install_bao
  print_finish
}

main "$@"
