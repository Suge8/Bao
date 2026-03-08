import importlib
import importlib.resources
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.config.schema import Config


class ConfigLoadError(Exception):
    """Raised when config file exists but cannot be parsed/validated."""


_JSONC_TEMPLATE = """\
{
  "config_version": 3,
  // 💡 环境变量可覆盖此文件中的任何配置 | Env vars override any config below
  //    命名 Naming: BAO_{SECTION}__{FIELD}  (snake_case, 双下划线分隔层级)
  //    示例 Examples: BAO_AGENTS__DEFAULTS__MODEL=xxx  BAO_PROVIDERS__NAME__API_KEY=sk-xxx
  //
  // ───────────────────────────────────────────────────────────────
  //  🤖 Agent 配置 | Agent Settings
  // ───────────────────────────────────────────────────────────────
  "agents": {
    "defaults": {
      "workspace": "~/.bao/workspace",
      // 主模型 | Main model
      // 格式 Format: "前缀/模型名" e.g. "openai/gpt-5.2", "deepseek/deepseek-chat"
      // 推荐 Recommended:
      //   "anthropic/claude-opus-4-6"
      //   "zai/glm-5"
      //   "moonshot/kimi-k2.5"
      //   "openai/gpt-5.2"
      "model": "",
      // 轻量模型（可选）：后台任务用，节省开销
      // Utility model (optional): for background tasks, saves cost
      "utilityModel": "",
      // 经验模型策略 | Experience model strategy
      //   "utility" — 用轻量模型(默认) | use utility model (default)
      //   "main"    — 用主模型 | use main model
      //   "none"    — 不调用 LLM | no LLM calls
      "experienceModel": "utility",
      // 可切换模型列表，运行时 /model 切换 | Switchable models, use /model at runtime
      "models": [],
      "maxTokens": 16000,
      "temperature": 0.1,
      "maxToolIterations": 50,
      "memoryWindow": 100,
      // 推理强度（可选）| Reasoning effort (optional)
      //   "low" | "medium" | "high"
      "reasoningEffort": null,
      // 上下文管理策略 | Context management strategy
      //   "off"        — 关闭，不做任何自动处理 | Disabled, no automatic handling
      //   "auto"       — 自动管理：大输出外置+上下文压实(推荐) | Auto: offload large outputs + compact context (recommended)
      //   "observe"    — 仅观察，零开销 | Observe only, zero overhead
      //   "aggressive" — 更激进的裁剪 | More aggressive trimming
      "contextManagement": "auto",
      // 是否向聊天渠道发送进度文本（默认开启）
      // Whether to send progress text to chat channels (enabled by default)
      "sendProgress": true,
      // 是否向聊天渠道发送工具调用提示（默认开启）
      // Whether to send tool-call hints to chat channels (enabled by default)
      "sendToolHints": true
    }
  },
  // ───────────────────────────────────────────────────────────────
  //  🔑 LLM Providers — 取消注释以启用 | Uncomment to enable
  //  ⚠️  请至少启用一个 | Enable at least one
  //  名称随意，type 决定 SDK | Name freely, type determines SDK
  //  type: "openai" | "anthropic" | "gemini" | "openai_codex"
  // ───────────────────────────────────────────────────────────────
  "providers": {
    // ── 示例 | Example ─────────────────────────
    // ── OpenAI 兼容 | OpenAI Compatible     //  适用 Supports: OpenAI, OpenRouter, Groq, Moonshot, GLM...
    // "provider-name": {
    //   "type": "openai",
    //   "apiKey": "sk-xxx",
    //   "apiBase": "https://api.openai.com/v1",  // 留空用官方，填代理地址自动兼容 | Empty for official, proxy auto-compatible
    // },
    // ── Anthropic ───────────────────────────────────────────────
    // "provider-name": {
    //   "type": "anthropic",
    //   "apiKey": "sk-xxx",
    //   "apiBase": ""                  // 留空用官方，填代理地址自动兼容 | Empty for official, proxy auto-compatible
    // },
    // ── Google Gemini ───────────────────────────────────────────
    // "provider-name": {
    //   "type": "gemini",
    //   "apiKey": "AI...",
    //   "apiBase": ""                  // 留空用官方 | Empty for official API
    // },
    // ── OpenAI Codex OAuth ────────────────────────────────────────
    //  通过 ChatGPT 订阅 OAuth 认证，无需 API Key | Auth via ChatGPT subscription, no API Key needed
    //  需安装 oauth-cli-kit 并完成登录 | Requires oauth-cli-kit login
    // "openai-codex": {
    //   "type": "openai_codex"
    // },
    // ── 添加更多 | Add more ─────────────────────────────────────
    // "your-provider-name": {
    //   "type": "openai",              // openai | anthropic | gemini | openai_codex
    //   "apiKey": "",
    //   "apiBase": ""
    // }
  },
  // ───────────────────────────────────────────────────────────────
  //  💬 聊天渠道 — 取消注释以启用 | Chat Channels — Uncomment to enable
  // ───────────────────────────────────────────────────────────────
  "channels": {
    // ── iMessage（推荐 Recommended）─────────────────────────────
    //  仅 macOS | macOS only
    // "imessage": {
    //   "enabled": true,
    //   "pollInterval": 2.0,
    //   "service": "iMessage",
    //   "allowFrom": []
    // },
    //
    // ── Telegram ────────────────────────────────────────────────
    //  Token from @BotFather
    // "telegram": {
    //   "enabled": true,
    //   "token": "123456:ABC-DEF...",
    //   "allowFrom": ["6374137703"],  // 私聊建议直接填数字 chat_id；需要兼容用户名时可填 "username|6374137703"
    //   "proxy": null,
    //   "replyToMessage": false
    // },
    //
    // ── Discord ─────────────────────────────────────────────────
    //  Bot Token + Message Content Intent
    // "discord": {
    //   "enabled": true,
    //   "token": "MTIz...",
    //   "allowFrom": []
    // },
    //
    // ── WhatsApp ────────────────────────────────────────────────
    //  通过 Bridge 扫码 | Connect via bridge, scan QR
    // "whatsapp": {
    //   "enabled": true,
    //   "bridgeUrl": "ws://localhost:3001",
    //   "bridgeToken": "",
    //   "allowFrom": []
    // },
    //
    // ── 飞书 Feishu / Lark ──────────────────────────────────────
    //  App ID + App Secret
    // "feishu": {
    //   "enabled": true,
    //   "appId": "",
    //   "appSecret": "",
    //   "encryptKey": "",
    //   "verificationToken": "",
    //   "allowFrom": []
    // },
    //
    // ── Slack ────────────────────────────────────────────────────
    //  Bot Token (xoxb-...) + App Token (xapp-...)
    // "slack": {
    //   "enabled": true,
    //   "botToken": "xoxb-...",
    //   "appToken": "xapp-...",
    //   "replyInThread": true,
    //   "reactEmoji": "eyes",
    //   "groupPolicy": "mention",
    //   "allowFrom": []
    // },
    //
    // ── 钉钉 DingTalk ───────────────────────────────────────────
    //  AppKey + AppSecret（Stream 模式 | Stream mode）
    // "dingtalk": {
    //   "enabled": true,
    //   "clientId": "",
    //   "clientSecret": "",
    //   "allowFrom": []
    // },
    //
    // ── QQ ───────────────────────────────────────────────────────
    //  App ID + Secret（botpy SDK）
    // "qq": {
    //   "enabled": true,
    //   "appId": "",
    //   "secret": "",
    //   "allowFrom": []
    // },
    //
    // ── Email 邮件 ──────────────────────────────────────────────
    //  IMAP 收件 + SMTP 发件 | IMAP receive + SMTP send
    // "email": {
    //   "enabled": true,
    //   "consentGranted": true,
    //   "imapHost": "imap.gmail.com",
    //   "imapPort": 993,
    //   "imapUsername": "",
    //   "imapPassword": "",
    //   "smtpHost": "smtp.gmail.com",
    //   "smtpPort": 587,
    //   "smtpUsername": "",
    //   "smtpPassword": "",
    //   "fromAddress": "",
    //   "allowFrom": []
    // },
    //
    // ── Mochat ───────────────────────────────────────────────────
    //  Mochat 客服集成 | Mochat customer service
    // "mochat": {
    //   "enabled": true,
    //   "baseUrl": "https://mochat.io",
    //   "clawToken": "",
    //   "agentUserId": "",
    //   "allowFrom": []
    // }
  },
  // ───────────────────────────────────────────────────────────────
  //  🔧 工具配置 | Tool Settings
  // ───────────────────────────────────────────────────────────────
  "tools": {
    // 网页搜索：填 Tavily / Brave / Exa API Key 启用 | Web search: fill Tavily / Brave / Exa API Key to enable
    "web": {
      "search": {
        "provider": "",
        "tavilyApiKey": "",
        "braveApiKey": "",
        "exaApiKey": ""
      }
    },
    "exec": {
      "timeout": 60,
      // 沙箱模式 | Sandbox mode
      //   "full-auto"  — 不拦任何命令 | No restrictions
      //   "semi-auto"  — 危险命令拦截+工作区限制(默认) | Deny dangerous commands + workspace restriction (default)
      //   "read-only"  — 只允许读操作 | Read-only commands only
      "sandboxMode": "semi-auto"
    },
    // 向量嵌入（可选）| Embedding (optional)
    "embedding": {
      "model": "",
      "apiKey": "",
      "baseUrl": ""
    },
    // 将 Agent 的所有文件和命令操作限制在工作区目录内｜Restrict all files and command operations of the Agent within the workspace directory.
    "restrictToWorkspace": false,
    // 图像生成：填 API Key 启用 | Image generation: fill API Key to enable
    "imageGeneration": {
      "apiKey": "",
      "model": "",
      "baseUrl": ""
    },
    // 桌面自动化：截屏/点击/输入等 | Desktop automation: screenshot/click/type etc.
    "desktop": {
      "enabled": true
    },
    // 工具暴露策略 | Tool exposure policy
    //   mode: auto(智能路由，按需曝光) | off(全量暴露)
    "toolExposure": {
      "mode": "auto"
    },
    // MCP tool 注册总上限（0 表示不限）| Global cap for registered MCP tools (0 = unlimited)
    "mcpMaxTools": 50,
    // 是否对 MCP schema 做精简（删除冗余元数据）| Slim MCP schema metadata before exposing to LLM
    "mcpSlimSchema": true,
    // MCP 服务器，兼容 Claude Desktop / Cursor｜MCP servers, compatible with Claude Desktop / Cursor
    // 每个 server 可覆盖全局策略：slimSchema / maxTools
    "mcpServers": {
      // "filesystem": {
      //   "command": "npx",
      //   "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
      //   "slimSchema": false,
      //   "maxTools": 16
      // }
    }
  },
  // ───────────────────────────────────────────────────────────────
  //  🖥️ Desktop UI | 桌面界面
  // ───────────────────────────────────────────────────────────────
  "ui": {
    "update": {
      // 桌面端更新：默认使用 GitHub Pages 上的稳定 feed
      // Desktop updates: defaults to the stable feed hosted on GitHub Pages
      "enabled": true,
      "autoCheck": true,
      "channel": "stable",
      "feedUrl": "https://suge8.github.io/Bao/desktop-update.json"
    }
  }
}
"""


def get_config_path() -> Path:
    from bao.utils.helpers import get_data_path

    base = get_data_path()
    jsonc = base / "config.jsonc"
    if jsonc.exists():
        return jsonc
    return base / "config.json"


def get_data_dir() -> Path:
    from bao.utils.helpers import get_data_path

    return get_data_path()


def ensure_first_run() -> bool:
    """Create ~/.bao/config.jsonc + workspace if they don't exist yet.

    Returns True if files were created (first run), False if already existed.
    Does NOT print, does NOT SystemExit — safe for Desktop use.
    """
    path = get_config_path()
    if path.exists():
        return False
    config = Config()
    save_config(config)
    _ensure_workspace(config)
    return True


def _handle_config_error(path: Path, error: Exception) -> Config:
    """Handle config parse/validation failure: backup, warn, and optionally raise."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".broken.{ts}{path.suffix}")
    try:
        shutil.copy2(path, backup)
    except OSError:
        backup = None

    parts: list[str] = ["", "❌ 配置文件有误 / Config file error", ""]
    parts.append(f"   📄 文件 File: {path}")

    if isinstance(error, json.JSONDecodeError):
        parts.append(
            f"   📍 位置 Location: 第 {error.lineno} 行, 第 {error.colno} 列"
            f" / line {error.lineno}, col {error.colno}"
        )
        parts.append(f"   💬 原因 Reason: {error.msg}")
        try:
            src = path.read_text(encoding="utf-8").splitlines()
            start = max(0, error.lineno - 3)
            end = min(len(src), error.lineno)
            if start < end:
                parts.append("")
                for i in range(start, end):
                    ln = i + 1
                    marker = " 👉" if ln == error.lineno else "   "
                    parts.append(f"  {marker} {ln:>4} | {src[i]}")
        except OSError:
            pass
    else:
        parts.append(f"   💬 原因 Reason: {error}")

    if backup:
        parts.append(f"   💾 已备份 Backup: {backup}")

    parts.append("")

    strict = os.environ.get("BAO_CONFIG_STRICT", "1") != "0"
    if strict:
        parts.append("   💡 修复后重新运行 / Fix and re-run: bao")
        parts.append("   💡 或跳过检查 / Or skip: BAO_CONFIG_STRICT=0 bao")
        parts.append("")
        print("\n".join(parts))
        raise SystemExit(1)

    parts.append("   ⚡ BAO_CONFIG_STRICT=0 → 使用默认配置继续 / Using defaults")
    parts.append("")
    print("\n".join(parts))
    return Config()


def _apply_env_overlay(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge BAO_* env vars into config data. Env wins over file."""
    from pydantic.alias_generators import to_camel

    prefix = "BAO_"
    delimiter = "__"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix) :].lower().split(delimiter.lower())
        if not parts or not parts[-1]:
            continue
        # Navigate to parent dict, creating intermediates as needed
        target = data
        for part in parts[:-1]:
            camel = to_camel(part)
            # Match existing key (camelCase or snake_case)
            if camel in target and isinstance(target[camel], dict):
                target = target[camel]
            elif part in target and isinstance(target[part], dict):
                target = target[part]
            else:
                target[camel] = {}
                target = target[camel]
        # Set leaf value — try JSON parse for booleans/numbers/arrays
        leaf = to_camel(parts[-1])
        if leaf not in target and parts[-1] in target:
            leaf = parts[-1]  # fallback to snake_case if already present
        try:
            target[leaf] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            target[leaf] = value
    return data


def load_config(config_path: Path | None = None) -> Config:
    path = config_path or get_config_path()

    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            text = _strip_jsonc_comments(text)
            data = json.loads(text)
            data = _migrate_config(data)
            data = _apply_env_overlay(data)
            return Config.model_validate(data)
        except Exception as e:
            return _handle_config_error(path, e)

    # Auto-init: first run — create config + workspace + templates, then exit cleanly
    ensure_first_run()
    actual = get_config_path()
    print(
        "\n📁 .bao 配置文件夹已创建 / .bao config folder created"
        "\n\n  📝 请编辑文件完成配置 / Please edit to configure:"
        f"\n     {actual}"
        "\n\n  ▶ 然后重新运行 / Then run: bao\n"
    )
    raise SystemExit(0)


def _dump_with_secrets(config: Config) -> dict[str, Any]:
    """Dump config to dict with SecretStr values exposed (for file persistence)."""
    from pydantic import BaseModel, SecretStr

    def _walk(obj: Any) -> Any:
        if isinstance(obj, SecretStr):
            return obj.get_secret_value()
        if isinstance(obj, BaseModel):
            data = obj.model_dump(by_alias=True)
            for field_name in obj.model_fields:
                val = getattr(obj, field_name)
                if not isinstance(val, (SecretStr, BaseModel, dict)):
                    continue
                fi = obj.model_fields[field_name]
                raw_key = fi.alias or field_name
                key = raw_key if isinstance(raw_key, str) else field_name
                if key not in data and hasattr(obj.model_config, "get"):
                    gen = obj.model_config.get("alias_generator")
                    if callable(gen):
                        generated = gen(field_name)
                        if isinstance(generated, str):
                            key = generated
                    else:
                        alias_fn = getattr(gen, "alias", None)
                        if callable(alias_fn):
                            generated = alias_fn(field_name)
                            if isinstance(generated, str):
                                key = generated
                if key not in data:
                    key = field_name
                if key in data:
                    data[key] = _walk(val)
            return data
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        return obj

    return _walk(config)


def save_config(config: Config, config_path: Path | None = None) -> None:
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix != ".jsonc" and not path.exists():
        path = path.with_suffix(".jsonc")

    if path.suffix == ".jsonc" and not path.exists():
        path.write_text(_JSONC_TEMPLATE, encoding="utf-8")
    else:
        data = _dump_with_secrets(config)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def _ensure_workspace(config: Config) -> None:
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)

    _deferred = {"PERSONA.md", "INSTRUCTIONS.md", "HEARTBEAT.md"}
    for item in importlib.resources.files("bao.templates.workspace").iterdir():
        if not item.name.endswith(".md") or item.name in _deferred:
            continue
        fp = workspace / item.name
        if not fp.exists():
            fp.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")

    (workspace / "skills").mkdir(exist_ok=True)


def _strip_jsonc_comments(text: str) -> str:
    normal = 0
    in_string = 1
    escape = 2
    line_comment = 3
    block_comment = 4

    state = normal
    block_depth = 0
    i = 0
    n = len(text)
    out: list[str] = []

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if state == normal:
            if ch == '"':
                out.append(ch)
                state = in_string
                i += 1
                continue
            if ch == "/" and nxt == "/":
                state = line_comment
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = block_comment
                block_depth = 1
                i += 2
                continue
            out.append(ch)
            i += 1
            continue

        if state == in_string:
            out.append(ch)
            if ch == "\\":
                state = escape
            elif ch == '"':
                state = normal
            i += 1
            continue

        if state == escape:
            out.append(ch)
            state = in_string
            i += 1
            continue

        if state == line_comment:
            if ch == "\n":
                out.append(ch)
                state = normal
            i += 1
            continue

        if ch == "/" and nxt == "*":
            block_depth += 1
            i += 2
            continue
        if ch == "*" and nxt == "/":
            block_depth -= 1
            i += 2
            if block_depth == 0:
                state = normal
            continue
        i += 1

    if state == 4 or block_depth != 0:  # block_comment
        raise ValueError("Unterminated block comment in config file")

    return "".join(out)


def _migrate_config(data: dict[str, Any]) -> dict[str, Any]:
    """Apply versioned migrations and print warnings."""
    migrate_config = importlib.import_module("bao.config.migrations").migrate_config

    data, warnings = migrate_config(data)
    for w in warnings:
        print(f"  ℹ️  {w}")
    return data
