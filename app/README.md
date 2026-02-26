# bao Desktop App (实验性)

基于 PySide6 + QML 的桌面客户端，**`bao` CLI 的纯 UI 壳子**。

所有核心逻辑（AgentLoop、Channels、Cron、Heartbeat、startup greeting、首次落盘）均来自 `bao/` core，Desktop 不重复实现任何业务逻辑。网关需用户手动启动（点击侧边栏 ⏻ 按钮），启动后桌面聊天窗口作为 `desktop` channel 与 Telegram、iMessage 等其他渠道共存运行。

当前窗口外观默认使用系统标题栏；在 Windows 上会尝试调用 DWM 请求原生圆角（Windows 11 效果最佳）。

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

首次运行自动创建 `~/.bao/config.jsonc` 与默认 workspace（`~/.bao/workspace/`），无需手动初始化。若 `agents.defaults.model` 为空或 providers 中未配置 apiKey，App 自动跳转 Settings 页面引导完成配置。

### 3. 使用流程

1. 打开 App → 若首次使用且未配置 Provider/Model，会自动跳转 Settings 页面；填写配置
2. 点击 Save → 切换到 Chat 页面，网关自动启动
3. Gateway 启动后，桌面聊天 + 所有已启用 Channels 同时运行
4. 可在标题栏右侧查看网关状态、停止或重启网关
5. 修改配置后点击 Save → 在标题栏点击重启即可应用

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--start-view chat\|settings` | 指定首屏（默认 `chat`） |
| `--smoke` | Smoke 测试模式：加载 QML 后 500ms 自动退出 |
| `--smoke-theme-toggle` | Smoke + 主题切换验证 |
| `--smoke-screenshot <path>` | Smoke + 截图保存（便于 UI 回归） |
| `--seed-messages` | 预填充示例消息（调试用） |
| `--qml <path>` | 覆盖 QML 入口文件 |

## 当前限制

- 配置保存后需手动重启 Gateway（非热重载，by design）

## 启动问候行为

- 启动问候由 `bao/gateway/builder.py:send_startup_greeting` 统一执行，CLI 和 Desktop 共用
- 每个已启用渠道独立调 LLM 生成问候，写入渠道真实 session（非孤立 system 会话）
- 跳过 `allow_from ≠ chat_id` 的渠道（discord/slack/mochat）；WhatsApp 自动拼 JID
- 重复目标自动去重，空 `chat_id` / 空主 ID 会被跳过并记录 warning
- 触发 prompt 通过 `process_direct(ephemeral=True)` 跳过持久化，桌面端 history 同步不可见
- Desktop 通过 `on_desktop_greeting` 回调接收问候（兼容 sync/async 回调）
- 所有发送与回调均为"失败隔离"策略：单个渠道异常不打断其他渠道
- Onboarding 阶段（语言选择/人设设置）广播静态消息，不调 LLM

## 聊天流式渲染说明

- Desktop 使用 provider 增量回调实时更新气泡内容（`gateway.py` 信号桥接到 Qt 主线程）
- 当一次回复包含多轮迭代（如中途触发工具调用）时，会在下一段真实增量到达时切到新 assistant 气泡，避免"内容先并入上一泡再跳走"的视觉抖动
- 当前选中的会话会自动做轻量 history 同步（1.2s），可实时看到 iMessage/Telegram 等外部渠道写入的新消息；本地发送流式期间会自动跳过同步，若此时切会话则延后到本轮发送结束后应用；history 异步回填带请求序号，旧结果会被丢弃，避免时序倒灌
- 会话切换时历史列表采用单次 model reset，并通过 `historyLoading` 门控临时关闭消息入场动画/滚动跟随，切换结束后一次性定位到最新消息；侧边栏会话列表在重建时保留底部锚点，避免滚到底部抖动回弹
- 会话切换采用乐观选中 + 过期选择回调丢弃（`SessionService` pending key），避免快速切换时被旧回调回滚到错误会话；消息区在 history 加载完成后通过 `followRetryTimer` 瞬时跳转到底部（`positionViewAtEnd` + `contentY = maxContentY`），不做渐进式滚动，确保切换后立即显示最新消息

## 打包

使用 Nuitka 编译为原生二进制，支持 macOS (arm64/x86_64) 和 Windows (x64)。

```bash
# macOS 本地构建
bash app/scripts/build_mac.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64

# Windows 本地构建
app\scripts\build_win.bat
iscc app\scripts\bao_installer.iss
```

推送 `v*` tag 自动触发 GitHub Actions 构建双平台安装包。

完整打包指南见 [`docs/desktop-packaging.md`](../docs/desktop-packaging.md)。

> 开发细节（架构、测试命令、UI 坑点、技术要点）见 `AGENTS.md`。
