import json
import importlib.resources
import re
from pathlib import Path
from typing import Any

from bao.config.schema import Config

_JSONC_TEMPLATE = """\
{
  // ╔═══════════════════════════════════════════════════════════════╗
  // ║  bao 配置文件 | bao Configuration                            ║
  // ╚═══════════════════════════════════════════════════════════════╝
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
      //   "zhipu/glm-5"
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
      "maxTokens": 8192,
      "temperature": 0.1,
      "maxToolIterations": 20,
      "memoryWindow": 50,
      // 是否向聊天渠道发送进度消息（如"正在处理…"）
      // Whether to send progress messages to chat channels
      "sendProgress": false,
      // 是否向聊天渠道发送工具调用提示（如 web_search("...")）
      // Whether to send tool-call hints to chat channels
      "sendToolHints": false
    }
  },
  // ───────────────────────────────────────────────────────────────
  //  🔑 LLM Providers — 取消注释以启用 | Uncomment to enable
  //
  //  ⚠️  请至少启用一个 | Enable at least one
  //  名称随意，type 决定 SDK | Name freely, type determines SDK
  //  type: "openai" | "anthropic" | "gemini"
  // ───────────────────────────────────────────────────────────────
  "providers": {
    // ── 示例 | Example ─────────────────────────
    // ── OpenAI 兼容 | OpenAI Compatible     //  适用 Supports: OpenAI, OpenRouter, Groq, Moonshot, GLM...
    // "provider-name": {
    //   "type": "openai",
    //   "apiKey": "sk-xxx",
    //   "apiBase": "https://api.openai.com/v1",  // 留空用官方，填代理地址自动兼容 | Empty for official, proxy auto-compatible
    //   "apiMode": "auto"              // "auto" | "responses" | "completions"
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
    // ── 添加更多 | Add more ─────────────────────────────────────
    // "your-provider-name": {
    //   "type": "openai",              // openai | anthropic | gemini
    //   "apiKey": "",
    //   "apiBase": ""
    // }
  },
  // ───────────────────────────────────────────────────────────────
  //  💬 聊天渠道 — 取消注释以启用 | Chat Channels — Uncomment to enable
  //  推荐 iMessage（macOS 零配置）| iMessage recommended (macOS, zero config)
  // ───────────────────────────────────────────────────────────────
  "channels": {
    // ── iMessage（推荐 Recommended）─────────────────────────────
    //  仅 macOS | macOS only
    //
    // "imessage": {
    //   "enabled": true,
    //   "pollInterval": 2.0,
    //   "service": "iMessage",
    //   "allowFrom": []
    // },
    //
    // ── Telegram ────────────────────────────────────────────────
    //  Token from @BotFather
    //
    // "telegram": {
    //   "enabled": true,
    //   "token": "123456:ABC-DEF...",
    //   "allowFrom": [],
    //   "proxy": null,
    //   "replyToMessage": false
    // },
    //
    // ── Discord ─────────────────────────────────────────────────
    //  Bot Token + Message Content Intent
    //
    // "discord": {
    //   "enabled": true,
    //   "token": "MTIz...",
    //   "allowFrom": []
    // },
    //
    // ── WhatsApp ────────────────────────────────────────────────
    //  通过 Bridge 扫码 | Connect via bridge, scan QR
    //
    // "whatsapp": {
    //   "enabled": true,
    //   "bridgeUrl": "ws://localhost:3001",
    //   "bridgeToken": "",
    //   "allowFrom": []
    // },
    //
    // ── 飞书 Feishu / Lark ──────────────────────────────────────
    //  App ID + App Secret
    //
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
    //
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
    //
    // "dingtalk": {
    //   "enabled": true,
    //   "clientId": "",
    //   "clientSecret": "",
    //   "allowFrom": []
    // },
    //
    // ── QQ ───────────────────────────────────────────────────────
    //  App ID + Secret（botpy SDK）
    //
    // "qq": {
    //   "enabled": true,
    //   "appId": "",
    //   "secret": "",
    //   "allowFrom": []
    // },
    //
    // ── Email 邮件 ──────────────────────────────────────────────
    //  IMAP 收件 + SMTP 发件 | IMAP receive + SMTP send
    //
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
    //
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
    // 网页搜索：填 Tavily 或 Brave API Key 启用
    // Web search: fill Tavily or Brave API Key to enable
    "web": {
      "search": {
        "provider": "",
        "tavilyApiKey": "",
        "braveApiKey": ""
      }
    },
    "exec": {
      "timeout": 60
    },
    // 向量嵌入（可选）| Embedding (optional)
    "embedding": {
      "model": "",
      "apiKey": "",
      "baseUrl": ""
    },
    "restrictToWorkspace": false,
    // MCP 服务器，兼容 Claude Desktop / Cursor
    // MCP servers, compatible with Claude Desktop / Cursor
    "mcpServers": {}
  }
}
"""



def _read_workspace_template(filename: str) -> str:
    """Read a template from bao/templates/workspace/ via importlib.resources."""
    return (
        importlib.resources.files("bao.templates.workspace")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )

_PERSONA_EN = """# Persona

## Identity

I am bao, a lightweight AI assistant.

- Helpful, friendly
- Concise, to the point
- Curious, eager to learn
- Accuracy over speed
- Protect user privacy and security
- Transparent in actions

## User

- **Name**: (your name)
- **Timezone**: (your timezone)
- **Language**: English
- **Communication style**: (casual/formal)
- **Role**: (your role, e.g. developer, researcher)
- **Interests**: (topics you care about)

## Special Instructions

(Any specific instructions for the assistant)
"""

_INSTRUCTIONS_EN = """# Instructions

## Language Policy

Always reply in the language set in the user's `PERSONA.md`.
When calling tools, use the user's language for natural-language arguments (e.g. search queries) unless the user explicitly requests otherwise.

## Guidelines

- Briefly state your intent before taking action (one sentence)
- Ask for clarification when requests are ambiguous
- Be concise, accurate, and friendly
- Avoid pure list/bullet-point dumps in responses

## Tool Use

Tool outputs are intermediate data, not final responses.
- Extract only facts relevant to the user's question
- Note uncertainty when sources conflict
- Synthesize into a concise conclusion before replying
- Do not expose raw JSON, logs, or technical details unless the user asks

Before calling a tool, ask yourself: can I answer reliably without it? If yes, answer directly.

### Search Strategy

If `web_search` is in your tool list, prefer it for information retrieval; otherwise use `web_fetch` to access search engine pages.

## Workspace

| File | Purpose |
|------|---------|
| `PERSONA.md` | Personality, user profile, special instructions |
| `INSTRUCTIONS.md` | Behavior rules (this file) |
| `HEARTBEAT.md` | Periodic tasks, checked every 30 minutes |
| `skills/` | Skill definitions (`skills/{name}/SKILL.md`) |

### Database (LanceDB — Auto-managed)

| Table | Purpose |
|-------|---------|
| `memory` | Long-term memory, conversation history, task experience |
| `memory_vectors` | Semantic embeddings (optional) |

Memory is auto-managed. Do not use `read_file`/`write_file`/`edit_file` on memory.
Experience learning runs automatically — no manual action needed.

## Identity & Preference Persistence

When the user mentions the following in conversation, use `edit_file` to update `PERSONA.md`:

- User info (name, timezone, language, preferences) → `## User`
- Assistant personality (nickname, style) → `## Identity`
- Behavioral preferences (e.g. "make search results more detailed") → `## Special Instructions`

`PERSONA.md` is loaded at the start of every conversation. If you don't write it, you'll forget.
Do not modify `INSTRUCTIONS.md` — write behavioral preferences to `PERSONA.md` special instructions.

## Scheduled Tasks

- Use the `cron` tool for reminders and scheduled tasks — don't just write to memory
- Edit `HEARTBEAT.md` for periodic tasks (checked every 30 minutes)
"""


LANG_PICKER = "嗨 👋 请选择语言 / Pick your language:\n\n1. 中文\n2. English"
PERSONA_GREETING: dict[str, str] = {
    "zh": (
        "嘿 👋 我是运行在 bao 框架里的 AI 搭子，还没名字呢～\n\n"
        "正式开工之前，先对个暗号：\n\n"
        "1. 给我起个名字呗？\n"
        "2. 你叫啥？怎么称呼你舒服怎么来～\n"
        "3. 平时聊天习惯？随意唠 / 说重点 / 正经点\n\n"
    ),
    "en": (
        "Hey 👋 I'm an AI buddy running on the bao framework — still unnamed tho~\n\n"
        "Before we get rolling, quick intro:\n\n"
        "1. Wanna give me a name?\n"
        "2. What do I call you? Whatever feels right~\n"
        "3. How do you like to chat? Chill / straight to the point / keep it professional\n\n"
    ),
}


def detect_onboarding_stage(workspace: Path) -> str:
    """Detect onboarding stage from file existence.
    Returns:
        'lang_select'  — no INSTRUCTIONS.md yet
        'persona_setup' — has INSTRUCTIONS.md but no PERSONA.md
        'ready'        — both files exist
    """
    if not (workspace / "INSTRUCTIONS.md").exists():
        return "lang_select"
    if not (workspace / "PERSONA.md").exists():
        return "persona_setup"
    return "ready"


def infer_language(workspace: Path) -> str:
    """Infer language from INSTRUCTIONS.md first line. Defaults to 'zh'."""
    inst = workspace / "INSTRUCTIONS.md"
    if not inst.exists():
        return "zh"
    first_line = inst.read_text(encoding="utf-8").split("\n", 1)[0]
    return "en" if first_line.strip().lower().startswith("# instructions") else "zh"


def write_instructions(workspace: Path, lang: str) -> None:
    """Write INSTRUCTIONS.md in the chosen language (deferred until onboarding)."""
    tpl = _INSTRUCTIONS_EN if lang == "en" else _read_workspace_template("INSTRUCTIONS.md")
    (workspace / "INSTRUCTIONS.md").write_text(tpl, encoding="utf-8")


def write_persona_profile(workspace: Path, lang: str, profile: dict[str, str]) -> None:
    """Write extracted user profile into PERSONA.md, replacing template placeholders."""
    persona = workspace / "PERSONA.md"
    base = _PERSONA_EN if lang == "en" else _read_workspace_template("PERSONA.md")
    content = base
    user_name = profile.get("user_name", "")
    timezone = profile.get("timezone", "")
    style = profile.get("style", "")
    role = profile.get("role", "")
    interests = profile.get("interests", "")
    nickname = profile.get("user_nickname", "")
    bot_name = profile.get("bot_name", "")

    if lang == "zh":
        replacements = {
            "（你的名字）": user_name,
            "（你的时区）": timezone,
            "（随意/正式）": style,
            "（你的角色，如开发者、研究员）": role,
            "（你关注的话题）": interests,
        }
    else:
        replacements = {
            "(your name)": user_name,
            "(your timezone)": timezone,
            "(casual/formal)": style,
            "(your role, e.g. developer, researcher)": role,
            "(topics you care about)": interests,
        }
    for old, new in replacements.items():
        if new:
            content = content.replace(old, new)
    # Update bot name in Identity section if provided
    if bot_name:
        if lang == "zh":
            content = content.replace(
                "我是运行在 bao 框架里的一个轻量级全能 AGENT。",
                f"我是{bot_name}，运行在 bao 框架里的一个轻量级全能 AGENT。",
            )
        else:
            content = content.replace(
                "I am bao, a lightweight AI assistant.",
                f"I am {bot_name}, a lightweight AI assistant.",
            )
    # Append user nickname if provided
    if nickname and nickname != user_name:
        name_val = user_name
        if lang == "zh":
            content = content.replace(
                f"- **姓名**：{name_val}",
                f"- **姓名**：{name_val}（称呼：{nickname}）",
            )
        else:
            content = content.replace(
                f"- **Name**: {name_val}",
                f"- **Name**: {name_val} (call me: {nickname})",
            )
    persona.write_text(content, encoding="utf-8")


def get_config_path() -> Path:
    base = Path.home() / ".bao"
    jsonc = base / "config.jsonc"
    if jsonc.exists():
        return jsonc
    return base / "config.json"


def get_data_dir() -> Path:
    from bao.utils.helpers import get_data_path

    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    path = config_path or get_config_path()

    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            text = _strip_jsonc_comments(text)
            data = json.loads(text)
            data = _migrate_config(data)
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")
        return Config()

    # Auto-init: first run — create config + workspace + templates, then exit cleanly
    config = Config()
    save_config(config)
    _ensure_workspace(config)
    actual = get_config_path()
    print(
        "\n📁 .bao 配置文件夹已创建 / .bao config folder created"
        "\n\n  📝 请编辑文件完成配置 / Please edit to configure:"
        f"\n     {actual}"
        "\n\n  ▶ 然后重新运行 / Then run: bao\n"
    )
    raise SystemExit(0)


def save_config(config: Config, config_path: Path | None = None) -> None:
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix != ".jsonc" and not path.exists():
        path = path.with_suffix(".jsonc")

    if path.suffix == ".jsonc" and not path.exists():
        path.write_text(_JSONC_TEMPLATE, encoding="utf-8")
    else:
        data = config.model_dump(by_alias=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def _ensure_workspace(config: Config) -> None:
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)

    _DEFERRED = {"PERSONA.md", "INSTRUCTIONS.md"}
    for item in importlib.resources.files("bao.templates.workspace").iterdir():
        if not item.name.endswith(".md") or item.name in _DEFERRED:
            continue
        fp = workspace / item.name
        if not fp.exists():
            fp.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")

    (workspace / "skills").mkdir(exist_ok=True)


def _strip_jsonc_comments(text: str) -> str:
    return re.sub(
        r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*[\s\S]*?\*/',
        lambda m: m.group() if m.group().startswith('"') else "",
        text,
    )


def _migrate_config(data: dict[str, Any]) -> dict[str, Any]:
    # --- providers: old fixed-key format → new dict+type format ---
    providers = data.get("providers", {})
    old_key_map = {"openaiCompatible": "openai", "openai_compatible": "openai"}
    for old_key, new_name in old_key_map.items():
        if old_key in providers:
            cfg = providers.pop(old_key)
            cfg.setdefault("type", "openai")
            providers.setdefault(new_name, cfg)
    for name in ("anthropic", "gemini"):
        if name in providers and isinstance(providers[name], dict):
            providers[name].setdefault("type", name)
    # --- tools migrations ---
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    search = tools.get("web", {}).get("search", {})
    if "apiKey" in search and "braveApiKey" not in search:
        search["braveApiKey"] = search.pop("apiKey")
    if "tavilyKey" in search and "tavilyApiKey" not in search:
        search["tavilyApiKey"] = search.pop("tavilyKey")
    return data
