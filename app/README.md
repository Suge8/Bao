# bao Desktop App (实验性)

基于 PySide6 + QML 的桌面客户端，**CLI `bao` 命令的 GUI 替代品**。

点击 Start Gateway 即可启动完整网关：AgentLoop + 全部已启用 Channels + Cron + Heartbeat，功能与 `bao` CLI 完全一致。桌面聊天窗口本身作为 `desktop` channel 与 Telegram、iMessage 等其他渠道共存。

> **⚠️ 实验性功能**：桌面端处于早期开发阶段，API 和行为可能随时变更。

## 快速开始

### 1. 安装依赖

```bash
uv sync --extra desktop
```

### 2. 启动应用

```bash
uv run python app/main.py
```

首次运行自动创建 `~/.bao/config.jsonc`。配置缺失或无效时 App 自动跳转 Settings 页面。

### 3. 使用流程

1. 打开 App → Settings 页面填写配置（Provider、Channels、Tools 等，与 `~/.bao/config.jsonc` 一一对应）
2. 点击 Save → 切换到 Chat 页面 → 点击 **Start Gateway**
3. Gateway 启动后，桌面聊天 + 所有已启用 Channels（Telegram、iMessage 等）同时运行
4. 修改配置后点击 Save → **Restart** 即可应用

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--start-view chat\|settings` | 指定首屏（默认 `chat`） |
| `--smoke` | Smoke 测试模式：加载 QML 后 500ms 自动退出 |
| `--smoke-theme-toggle` | Smoke + 主题切换验证 |
| `--smoke-screenshot <path>` | Smoke + 截图保存（便于 UI 回归） |
| `--seed-messages` | 预填充示例消息（调试用） |
| `--qml <path>` | 覆盖 QML 入口文件 |

## 运行测试

```bash
uv run --extra desktop --extra dev pytest \
  tests/test_asyncio_runner.py \
  tests/test_chat_model.py \
  tests/test_jsonc_patch.py \
  tests/test_config_service.py \
  tests/test_chat_service.py \
  tests/test_session_service.py \
  -q

# Smoke 测试（无头模式）
QT_QPA_PLATFORM=offscreen uv run --extra desktop python app/main.py --smoke

# Smoke 截图（无头模式）
QT_QPA_PLATFORM=offscreen uv run --extra desktop python app/main.py \
  --smoke-screenshot .sisyphus/evidence/ui-chat.png \
  --start-view chat
```

## 开发备注

- QML 8 位十六进制颜色字面量使用 `#AARRGGBB`（不是前端常见的 `#RRGGBBAA`）。例如 `#08FFFFFF` 表示 3% 透明的白色。

## UI 坑点（给后续 Agent）

- `--smoke-screenshot <path>` 是“截图后自动退出”模式，窗口闪一下就结束是预期行为，不是崩溃。
- 圆角窗口不要依赖 `setMask()`：当前插件会报 `This plugin does not support setting window masks`。正确做法是 `ApplicationWindow.color: "transparent"` + 单一外层圆角容器绘制。
- 顶部圆角若出现锯齿/台阶，优先检查是否“多层重复绘制”了标题栏背景。当前实现中 `titleBar` 用 `Item`（不额外上色）来避免双层边缘。
- 语言切换必须走 `Main.qml` 的响应式 `strings` 字典；不要再新增 `t("...")` 这类函数式读取，容易出现绑定不刷新。
- 语言持久化必须写对象：`{"ui": {"language": "zh"}}`。不要写点路径 `ui.language`，否则在当前 JSONC patch 逻辑下可能保存失败。
- 自动语言识别优先走 Python 侧 `detect_system_ui_language()`（`QLocale.system().uiLanguages()` + macOS `AppleLanguages` 兜底），QML 只消费 `systemUiLanguage`。
- 设计目标：`auto` 不增加配置负担，默认直接跟随系统 UI 语言；手动 `中文/English` 仅作为覆盖项。
- Settings 页字段本地化规则：
  - 公共壳层文案走 `Main.qml` 的 `strings`。
  - 字段级文案在 `SettingsView.qml` 统一使用 `tr(zh, en)`，禁止再写裸英文常量。
  - 新增字段时必须同步补中英文，避免“切中文后部分标签仍英文”。

## 架构概览

```
app/
├── main.py                 # 入口：参数解析、QML 引擎、后端注入
├── backend/
│   ├── asyncio_runner.py   # 独立线程 asyncio 事件循环
│   ├── chat.py             # ChatMessageModel (QAbstractListModel)
│   ├── gateway.py          # ChatService：完整网关生命周期（= CLI run_gateway）
│   ├── session.py          # SessionService + SessionListModel
│   ├── config.py           # ConfigService：JSONC 读取/校验/保存
│   └── jsonc_patch.py      # JSONC 无损 patch 写回（保留注释）
├── qml/
│   ├── Main.qml            # 主窗口：无边框标题栏 + Sidebar + StackLayout
│   ├── Sidebar.qml         # 导航按钮 + 会话列表
│   ├── ChatView.qml        # 消息列表 + 网关状态栏 + Start/Restart 按钮
│   ├── SettingsView.qml    # 配置表单（1:1 对齐 config.jsonc 全部字段）
│   ├── MessageBubble.qml   # 聊天气泡（user/assistant/system 三种角色）
│   ├── NavButton.qml       # 侧边栏导航按钮
│   ├── SessionItem.qml     # 会话列表项（hover 删除）
│   ├── SettingsSection.qml # 设置分组卡片
│   ├── SettingsField.qml   # 文本输入字段
│   └── ChannelRow.qml      # Channel 开关 + 动态字段列表
└── resources/
    └── .gitkeep
```

## 技术要点

- **完整网关**：Gateway 启动时创建 AgentLoop + ChannelManager + CronService + HeartbeatService，与 CLI `bao` 命令功能完全一致
- **多 Channel 共存**：桌面聊天窗口作为 `desktop` channel，与 Telegram、iMessage、Discord 等配置中启用的渠道同时运行
- **线程模型**：Qt 主线程负责 UI，AsyncioRunner 在独立线程运行 asyncio 事件循环，agent.run() 和 channels.start_all() 作为后台 Task 并发执行
- **Signal 跨线程**：所有 asyncio→Qt 回调通过内部 Signal 自动 marshal 到主线程，杜绝 QTimer 跨线程警告
- **手动启动**：用户在 ChatView 点击 Start Gateway 手动控制，非自动启动
- **错误可见**：网关初始化失败以系统消息形式显示在聊天区域
- **打字机效果**：`QTimer.singleShot` 以 20ms/4字符 节奏逐步更新 ChatMessageModel
- **JSONC 无损写回**：tokenizer-based parser 记录字节区间，patch 从右往左应用，注释/格式零损失
- **1:1 配置对齐**：Settings 页面字段与 `~/.bao/config.jsonc` 模板完全一致
- **UI 样式稳定**：启动时强制 `Qt Quick Controls = Basic` 并禁用 QML 磁盘缓存，避免环境覆盖导致样式漂移
- **切页布局稳定**：Chat/Settings 在 `StackLayout` 中按页动态加载，规避切回 Settings 后输入框宽度塌陷
- **Provider 延迟加载**：`bao.providers` 按需 import，未使用的 Provider 缺少依赖不会导致启动失败

## 当前限制

- 模拟流式输出（非真 token streaming，P1 计划）
- 配置保存后需手动重启 Gateway（非热重载，by design）
- 仅支持从源码运行（打包为 P2 计划）
