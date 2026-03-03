# Bao Desktop App (实验性)

基于 PySide6 + QML 的桌面客户端，**Bao 的 `bao` CLI 纯 UI 壳子**。

所有核心逻辑（AgentLoop、Channels、Cron、Heartbeat、startup greeting、首次落盘）均来自 `bao/` core，Desktop 不重复实现任何业务逻辑。启动问候由 core 侧轻量 `provider.chat` 生成（PERSONA.md 置于 system prompt 最前面锚定语气 + CJK 本地化时间 + 原生语言 user trigger，不注入工具/技能上下文）；desktop 问候与外部渠道并发触发，减少跨渠道串行等待。发送成功会打印 `💬 启动问候 / out` 日志（60 字预览），轻量路径失败时自动回退到 `process_direct(ephemeral=True)` 保底发送。网关需用户手动启动（点击侧边栏网关胶囊），启动后桌面聊天窗口作为 `desktop` channel 与 Telegram、iMessage 等其他渠道共存运行。

当前窗口外观默认使用系统标题栏；在 Windows 上会尝试调用 DWM 请求原生圆角（Windows 11 效果最佳）。

> **⚠️ 实验性功能**：桌面端处于早期开发阶段，API 和行为可能随时变更。

## 快速开始

如果你是首次安装 Bao CLI，建议先按仓库根目录 `README.md` 的「一键安装」完成环境准备，再继续桌面端步骤。

### 1. 安装依赖

```bash
uv sync --extra desktop
```

### 2. 启动应用

```bash
uv run python app/main.py
```

首次运行自动创建 `~/.bao/config.jsonc`（包含 `config_version`）与默认 workspace（`~/.bao/workspace/`），无需手动初始化。若 `agents.defaults.model` 为空或 providers 中未配置 apiKey，App 自动跳转 Settings 页面引导完成配置（OpenAI 兼容端点无需额外 `apiMode` 设置）。`Save` 成功后会立即恢复有效状态（`isValid=true`）；若 JSONC patch 失败会返回可见错误（`Patch failed`），不会让界面调用崩溃。

聊天渲染已做收口防闪：reply finalize 后的 history refresh 仅在 `role/content/format/status` 存在渲染差异时才会触发全量 reset；仅 `entrance` 元数据差异会被视为等价并跳过重载。delegate 的 `role` 兜底统一为 `assistant`，避免重建空窗误闪 user 样式大气泡。

### 3. 使用流程

1. 打开 App → 若首次使用且未配置 Provider/Model，会自动跳转 Settings 页面；填写配置
2. 点击 Save → 切换到 Chat 页面，网关自动启动
3. Gateway 启动后，桌面聊天 + 所有已启用 Channels 同时运行
4. 可在标题栏右侧查看网关状态、停止或重启网关
5. 修改配置后点击 Save → 在标题栏点击重启即可应用
6. 左侧 Sidebar 的 Plan 面板会实时展示当前会话计划（目标、进度、步骤状态）；计划清空后自动收起并显示最近完成摘要
7. 在 Settings 点击“+ 添加 LLM 提供商”后，新增项会自动展开并滚动到该卡片位置，方便直接填写
8. Settings 的 Agent Defaults 新增推理强度选项：`Auto` / `off` / `low` / `medium` / `high`（保存后重启 Gateway 生效）

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

## 打包

使用 Nuitka 编译为原生二进制，支持 macOS (arm64/x86_64) 和 Windows (x64)。

```bash
# macOS 本地构建
bash app/scripts/build_mac.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64

# Windows 本地构建
app\scripts\build_win.bat
app\scripts\package_win_installer.bat
```

推送 `v*` tag 自动触发 GitHub Actions 构建双平台安装包（`desktop-release.yml`）；PR/非 tag push 使用轻量流水线 `desktop-ci-lite.yml` 做依赖可安装性与脚本校验。

`v0.3.0` 为当前发布版本，详见 [`../CHANGELOG.md`](../CHANGELOG.md)。

完整打包指南见 [`docs/desktop-packaging.md`](../docs/desktop-packaging.md)。

补充：Desktop 后端已增加 `AsyncioRunner` 关闭收敛（先排空再取消残留任务）与 `SessionService.shutdown()` 生命周期清理，用于降低 Qt 测试批量运行时的间歇性崩溃风险。

补充：Settings 下拉字段统一走 `SettingsSelect.qml` 的自定义样式（输入框、箭头动效、弹层选项列表），避免平台默认下拉外观不一致。

> 开发细节（架构、测试命令、UI 坑点、技术要点）见 `AGENTS.md`。
