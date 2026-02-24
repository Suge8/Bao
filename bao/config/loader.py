import json
import re
from pathlib import Path

from bao.config.schema import Config

_JSONC_TEMPLATE = """\
{
  // ═══════════════════════════════════════════════════════════
  // 🤖 Agent 配置
  // ═══════════════════════════════════════════════════════════
  "agents": {
    "defaults": {
      "workspace": "~/.bao/workspace",
      // 主模型：用于对话和工具调用
      "model": "anthropic/claude-opus-4-5",
      // 轻量模型（可选）：用于经验提取和记忆整合等后台任务，节省主模型开销
      // 推荐: "openrouter/google/gemini-flash-1.5" 或 "deepseek/deepseek-chat"
      "utilityModel": "",
      // 经验/轨迹压缩使用的模型："utility"(默认,用轻量模型) | "main"(用主模型) | "none"(零成本规则,不调LLM)
      "experienceModel": "utility",
      // 可切换的模型列表，运行时用 /model 命令切换
      "models": [],
      "maxTokens": 8192,
      "temperature": 0.1,
      // 单次对话最大工具调用轮数
      "maxToolIterations": 20,
      // 记忆窗口：保留最近多少条消息在上下文中
      "memoryWindow": 50,
      // 是否向外部渠道（Telegram/Discord 等）发送思考过程进度 / Stream reasoning progress to external channels
      // 默认关闭，开启后外部渠道可看到 agent 实时思考片段
      "sendProgress": false,
      // 是否向外部渠道发送工具调用提示 / Send tool-hint messages to external channels
      "sendToolHints": false
    }
  },

  // ═══════════════════════════════════════════════════════════
  // 🔑 LLM Providers — 简化为 3 种类型，覆盖 99% 需求
  // ═══════════════════════════════════════════════════════════
  "providers": {
    // OpenAI 兼容端点：OpenAI, OpenRouter, DeepSeek, Groq, SiliconFlow, 火山引擎, 阿里云 DashScope, 月之暗面 Moonshot, 智谱 Zhipu, Ollama, LM Studio, vLLM, AiHubMix 等
    // 使用 model 格式: "openai/gpt-4o", "openrouter/anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat" 等
    "openaiCompatible": { "apiKey": "", "apiBase": "", "extraHeaders": {}, "apiMode": "auto" },
    // Anthropic 官方: Claude 系列模型
    // 使用 model 格式: "anthropic/claude-opus-4-5", "anthropic/claude-sonnet-4-20250514" 等
    "anthropic": { "apiKey": "" },
    // Google Gemini 官方: Gemini 系列模型
    // 使用 model 格式: "gemini/gemini-2.0-flash-exp" 等
    "gemini": { "apiKey": "" },
    // OpenAI Codex: OAuth 登录方式，暂不支持
    "openaiCodex": { "apiKey": "" }
  },

  // ═══════════════════════════════════════════════════════════
  // 💬 聊天渠道 — 按需启用
  // ═══════════════════════════════════════════════════════════
  "channels": {
    "telegram": { "enabled": false, "token": "", "allowFrom": [] }
  },

  // ═══════════════════════════════════════════════════════════
  // 🔧 工具配置
  // ═══════════════════════════════════════════════════════════
  "tools": {
    // web_search 搜索引擎：填 Tavily 或 Brave 任一 API Key 即可启用
    // provider: 优先使用的引擎 ("tavily" 或 "brave"，留空则自动选有 key 的)
    "web": { "search": { "provider": "", "tavilyApiKey": "", "braveApiKey": "" } },
    "exec": { "timeout": 60 },
    // 向量嵌入（可选）：启用后记忆和经验支持语义搜索
    // model: OpenAI 兼容的 embedding 模型名
    // apiKey: 对应 Provider 的 API Key
    // baseUrl: 非 OpenAI 官方时需填自定义端点
    "embedding": { "model": "", "apiKey": "", "baseUrl": "" },
    "restrictToWorkspace": false,
    // MCP 服务器，格式兼容 Claude Desktop / Cursor
    "mcpServers": {}
  }
}
"""

_WORKSPACE_TEMPLATES: dict[str, str] = {
    "PERSONA.md": """# 人设

## 身份

我是 bao，一个轻量级 AI 助手。

- 乐于助人、友善
- 简洁、切中要点
- 好奇、乐于学习
- 准确优先于速度
- 保护用户隐私和安全
- 行动透明

## 用户

- **姓名**：（你的名字）
- **时区**：（你的时区）
- **语言**：中文
- **沟通风格**：（随意/正式）
- **角色**：（你的角色，如开发者、研究员）
- **兴趣领域**：（你关注的话题）

## 特殊指令

（对助手行为的任何特定指令）
""",
    "INSTRUCTIONS.md": """# 指令

## 行为准则

- 在执行操作前，始终先说明你要做什么
- 当请求含糊不清时，主动询问确认
- 使用工具来协助完成任务
- 简洁、准确、友善

## 工作区架构

你的工作区包含以下组件：

### 文件

| 文件 | 用途 |
|------|------|
| `PERSONA.md` | 你的人格、价值观和用户档案 |
| `INSTRUCTIONS.md` | 行为规则和工作区文档（本文件） |
| `HEARTBEAT.md` | 定期任务清单，每 30 分钟检查一次 |
| `skills/` | 自定义技能定义（`skills/{name}/SKILL.md`） |

### 数据库（LanceDB — 自动管理）

| 表 | 用途 |
|----|------|
| `memory` | 长期记忆（`key='long_term'`）、对话历史（`type='history'`）和任务经验（`type='experience'`） |
| `memory_vectors` | 可选的语义嵌入，用于记忆和经验搜索 |

### 记忆规则

记忆存储在 LanceDB 中，自动管理。
不要对记忆使用 `read_file`/`write_file`/`edit_file`。
只需确认你需要记住的内容 — 它会在对话整合时自动保存。

### 经验学习（ExperienceLoop）

系统通过闭环反馈循环自动从已完成的任务中学习：

1. 每次任务完成后（使用了 ≥2 个工具或出现错误），系统会提取教训、搜索关键词和推理链，存储为 LanceDB 中的 `type='experience'`
2. 每条经验包含：任务描述、结果（成功/部分成功/失败）、质量评分（1-5）、分类、可操作的教训、搜索关键词、使用计数器（使用次数/成功次数）和推理链
3. 当类似任务出现时，过往经验会被检索并注入到系统提示中
4. 失败的任务会作为警告（⚠️）保留，与正面经验一起呈现，防止重复犯错

#### 经验生命周期

- **质量评分**：每条经验评分 1-5，评分越高在搜索中排名越前。
- **统计置信度**：每条经验跟踪 使用次数/成功次数 计数器。置信度 = 成功次数/使用次数（≥2 次后校准）。≥3 次使用后质量自动调整：成功率 ≥80% → 质量 +1，<40% → 质量 -1。
- **反馈循环**：任务成功完成时记录复用事件（使用次数+1，成功次数+1）。失败则弃用类似的过时经验。
- **冲突检测**：当同一分类下检索到的经验结论矛盾时，会标记 ⚡ 以提醒模型。
- **推理链追踪**：每条经验捕获 agent 中间推理步骤的摘要，存储为 `[Trace]` 以提供更丰富的上下文。
- **分类**：`coding`、`search`、`file`、`config`、`analysis`、`general` — 用于分组和合并。
- **关键词**：每条经验存储 2-5 个搜索关键词，增强超越语义相似性的检索能力。
- **时间衰减**：较旧的经验逐渐降低排名权重（半衰期约 35 天）。新鲜的教训优先。
- **负面学习**：失败的经验会被保留（而非仅弃用），并作为警告呈现，防止重复犯同样的错误。
- **自动清理**：弃用超过 30 天的条目和质量为 1 且超过 90 天的条目会被自动移除。
- **合并**：当同一分类下的经验累积达 ≥3 条时，会定期合并为简洁的高层原则。
- **排名**：搜索结果按 `质量 × 时间衰减 × 置信度` 排序，确保最好、最可靠、最新的经验优先呈现。

搜索模式：
- **有嵌入模型时**：语义向量搜索（质量更高）
- **无嵌入模型时**：关键词匹配降级搜索（仍可工作）

如果在 `agents.defaults` 中配置了 `utilityModel`，经验提取和记忆整合会使用该轻量模型，而非主模型。

经验条目自动管理 — 无需手动操作。

### 工具策略

当 `web_search` 工具可用时（配置了 Tavily/Brave API key），系统会在 System Prompt 中注入优先使用提示。始终优先使用 `web_search` 搜索信息，而非用 `exec` + `curl` 手动调用 API 或用 `web_fetch` 逐个抓取网页。

### 日志

- 默认输出 INFO 级别日志（简洁）
- 使用 `bao gateway -v` 启用 DEBUG 级别详细日志

## 首次使用引导（Onboarding）

Gateway 启动时自动检测 `PERSONA.md` 是否仍为模板状态。
若是新用户，系统会发送双语语言选择器（不调用 LLM），用户回复 1（中文）或 2（English）后：

1. `PERSONA.md` 被覆写为对应语言的模板
2. 你收到引导提示，用选定语言与用户完成初始设置（姓名、昵称、沟通风格）
3. 收集到信息后，立即用 `edit_file` 写入 `PERSONA.md`

引导完成后，后续启动走正常问候流程。

## 身份与偏好持久化

当用户告诉你以下内容时，立即使用 `edit_file` 更新 `PERSONA.md`：

- **用户的姓名/昵称、时区、语言、偏好** → 更新 `## 用户` 部分
- **你的昵称、人格特征、沟通风格** → 更新 `## 身份` 部分

`PERSONA.md` 在每次对话开始时加载。如果你不写入，下次就会忘记。

## 定时提醒
如果已安装 `cron` skill，使用 `cron` 工具创建提醒：

```
cron(action="add", message="你的消息", at="<ISO datetime>")
```

不要只是把提醒写入记忆 — 那不会触发实际通知。

## 心跳任务

`HEARTBEAT.md` 每 30 分钟检查一次。通过编辑此文件来管理定期任务：

```
- [ ] 检查日历并提醒即将到来的事件
- [ ] 扫描收件箱查看紧急邮件
```

当用户要求定期任务时，更新 `HEARTBEAT.md` 而不是创建一次性提醒。
""",
    "HEARTBEAT.md": """# 心跳任务

此文件每 30 分钟由 bao agent 自动检查。
在下方添加你希望 agent 定期执行的任务。

如果此文件没有任务（只有标题和注释），agent 会跳过本次心跳。

## 进行中的任务

<!-- 在此行下方添加你的定期任务 -->


## 已完成

<!-- 将已完成的任务移到这里或删除 -->

""",
}

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

_ONBOARDING_MARKERS = ("（你的名字）", "(your name)")


def is_new_user(workspace: Path) -> bool:
    """Check if PERSONA.md is still in template state."""
    persona = workspace / "PERSONA.md"
    if not persona.exists():
        return True
    content = persona.read_text(encoding="utf-8")
    return any(marker in content for marker in _ONBOARDING_MARKERS)


def apply_persona_language(workspace: Path, lang: str) -> None:
    """Overwrite PERSONA.md with the chosen language template."""
    persona = workspace / "PERSONA.md"
    template = _PERSONA_EN if lang == "en" else _WORKSPACE_TEMPLATES["PERSONA.md"]
    persona.write_text(template, encoding="utf-8")


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

    # Auto-init: first run — create config + workspace + templates
    config = Config()
    save_config(config)
    _ensure_workspace(config)
    actual = get_config_path()
    print(f"\n✓ Config created: {actual}")
    print(f"✓ Workspace created: {config.workspace_path}")
    print(f"\n  Edit config and add your API key:\n     {actual}")
    print("  Then run: bao\n")
    return config


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

    for filename, content in _WORKSPACE_TEMPLATES.items():
        fp = workspace / filename
        if not fp.exists():
            fp.write_text(content, encoding="utf-8")

    (workspace / "skills").mkdir(exist_ok=True)


def _strip_jsonc_comments(text: str) -> str:
    return re.sub(
        r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*[\s\S]*?\*/',
        lambda m: m.group() if m.group().startswith('"') else "",
        text,
    )


def _migrate_config(data: dict) -> dict:
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
