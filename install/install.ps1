$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$UvInstallUrl = "https://astral.sh/uv/install.ps1"
$MinPython = "3.11"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Has-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-Windows {
    if (-not $env:OS -or $env:OS -ne "Windows_NT") {
        Fail "🖥️ 仅支持 Windows / Windows only"
    }
}

function Ensure-Uv {
    if (Has-Command "uv") {
        Write-Ok "✅ uv 已就绪 / uv is ready"
        return
    }

    Write-Info "📦 正在安装 uv / Installing uv"
    try {
        irm $UvInstallUrl | iex
    }
    catch {
        Fail "❌ uv 安装失败 / Failed to install uv"
    }

    $LocalBin = Join-Path $HOME ".local\bin"
    if (Test-Path $LocalBin) {
        $env:Path = "$LocalBin;$env:Path"
    }

    if (-not (Has-Command "uv")) {
        Fail "❌ 已安装但未找到 uv，请检查 PATH / uv not found in PATH"
    }

    Write-Ok "✅ uv 安装完成 / uv installed"
}

function Ensure-Python {
    Write-Info "🐍 准备 Python $MinPython / Installing Python $MinPython"
    try {
        uv python install $MinPython
    }
    catch {
        Fail "❌ Python 安装失败 / Failed to install Python $MinPython"
    }
    Write-Ok "✅ Python 已就绪 / Python is ready"
}

function Install-Bao {
    Write-Info "🚀 正在安装 bao-ai / Installing bao-ai from PyPI"
    try {
        uv tool install --upgrade bao-ai
    }
    catch {
        Fail "❌ bao-ai 安装失败 / Failed to install bao-ai"
    }

    Write-Info "🔎 正在验证安装 / Verifying installation"
    try {
        uvx --from bao-ai bao --version | Out-Null
    }
    catch {
        Fail "❌ bao 命令验证失败 / Failed to verify bao"
    }
    Write-Ok "✅ bao-ai 安装成功 / bao-ai installed"
}

function Print-Finish {
    Write-Host ""
    Write-Ok "🎉 全部完成 / All done."
    Write-Info "👉 现在运行 bao 即可使用 / Run 'bao' to start"
    if (-not (Has-Command "bao")) {
        Write-Info "🛠️ 若找不到 bao，请重开终端或加入 PATH / If 'bao' is not found, reopen terminal or add PATH:"
        Write-Info "$HOME\.local\bin"
    }
}

Write-Info "🍞 Bao 一键安装（Windows）/ Bao one-click installer (Windows)"
Ensure-Windows
Ensure-Uv
Ensure-Python
Install-Bao
Print-Finish
