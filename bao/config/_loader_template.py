"""Default JSONC template for first-run config bootstrap."""

JSONC_TEMPLATE = """\
{
  "config_version": 6,
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
      //   "anthropic/claude-sonnet-4-6"
      //   "zai/glm-5"
      //   "moonshot/kimi-k2.5"
      //   "openai/gpt-5.4"
      "model": "",
      // 轻量模型（可选）：后台任务用，节省开销
      // Utility model (optional): for background tasks, saves cost
      "utilityModel": "",
      // 可切换模型列表，运行时 /model 切换 | Switchable models, use /model at runtime
      "models": [],
      "maxTokens": 16000,
      "temperature": 0.1,
      "maxToolIterations": 50,
      "memory": {
        // 最近保留多少条消息作为对话上下文 | Recent messages kept in prompt context
        "recentWindow": 100,
        // 自动学习经验的模型来源 | Model used for automatic learning
        //   "utility" — 用轻量模型(默认) | use utility model (default)
        //   "main"    — 用主模型 | use main model
        //   "none"    — 关闭自动学习 | disable automatic learning
        "learningMode": "utility"
      },
      // 推理强度（可选）| Reasoning effort (optional)
      //   "off" | "low" | "medium" | "high"
      "reasoningEffort": "off",
      // 服务档位（可选，OpenAI/Codex/兼容中转）| Service tier (optional, OpenAI/Codex/compatible relays)
      //   "priority" — 更快响应 | faster responses
      //   "flex"     — 更低成本，延迟可能波动 | lower cost, latency may vary
      "serviceTier": null,
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
  //  注意：openai_codex 这里是“聊天模型 Provider”，不是 coding_agent 里的 Codex CLI 工具
  //  Note: openai_codex here is the chat-model provider, not the Codex CLI backend used by coding_agent
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
    // 编程代理 `coding_agent(agent="codex")` / `opencode` / `claudecode`
    // 不在这里额外配置；只需本机安装对应 CLI 并完成登录
    // `codex` 会按 Bao 会话自动续接并持久化 session；若外部 session 失效，会清理后提示你重试一次
    // Coding agents are not configured here; install the CLI locally and authenticate first.
    // `codex` sessions auto-resume per Bao chat and are persisted; stale sessions are cleared with an explicit retry hint.
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
      //   "semi-auto"  — 仅拦明显危险命令（默认）| Deny obviously dangerous commands only (default)
      //   "read-only"  — 只允许读操作，并强制限制到工作区 | Read-only commands only, with workspace restriction
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
    //   mode: off(默认，全量暴露) | auto(BM25 域路由，按需曝光)
    //   domains:
    //     core               基础本地工具，始终保留 | core local tools, always kept
    //     messaging          发消息闭环 | messaging closure
    //     handoff            跨会话接力闭环 | session handoff closure
    //     web_research       网页搜索/抓取 | web search and fetch
    //     desktop_automation 桌面点击/输入/截屏 | desktop automation
    //     coding_backend     文件编辑 + coding backends | file editing + coding backends
    "toolExposure": {
      "mode": "off",
      "domains": [
        "core",
        "messaging",
        "handoff",
        "web_research",
        "desktop_automation",
        "coding_backend"
      ]
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
