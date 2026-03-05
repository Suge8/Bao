# Bao Desktop App (实验性)

基于 PySide6 + QML 的桌面客户端，**Bao 的 `bao` CLI 纯 UI 壳子**。

所有核心逻辑（AgentLoop、Channels、Cron、Heartbeat、startup greeting、首次落盘）均来自 `bao/` core，Desktop 不重复实现任何业务逻辑。启动问候由 core 侧轻量 `provider.chat` 生成；若配置了 `agents.defaults.utilityModel` 则优先使用 utility provider+model（PERSONA.md 置于 system prompt 最前面锚定语气 + CJK 本地化时间 + 原生语言 user trigger，不注入工具/技能上下文）；desktop 问候与外部渠道并发触发，外部渠道发送前会等待对应 channel ready；desktop 侧会先缓存问候，待会话 active 就绪事件发出后再按 active 会话落库/显示。发送成功会打印 `💬 启动问候 / out` 日志（60 字预览），轻量路径失败时回退到发送 presence 文本保底。网关需用户手动启动（点击侧边栏网关胶囊），启动后桌面聊天窗口作为 `desktop` channel 与 Telegram、iMessage 等其他渠道共存运行。

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

首次运行自动创建 `~/.bao/config.jsonc`（包含 `config_version`）与默认 workspace（`~/.bao/workspace/`），无需手动初始化。若 `agents.defaults.model` 为空或 providers 中未配置 apiKey，App 自动跳转 Settings 页面引导完成配置（OpenAI 兼容端点无需额外 `apiMode` 设置；OpenAI / Anthropic / Gemini 的 `apiBase` 缺版本段会自动补齐，传入完整 endpoint 会规范回版本 base）。`Save` 成功后会立即恢复有效状态（`isValid=true`）；若 JSONC patch 失败会返回可见错误（`Patch failed`），不会让界面调用崩溃。

聊天渲染已做收口防闪：reply finalize 后的 history refresh 仅在 `role/content/format/status` 存在渲染差异时才会触发全量 reset；仅 `entrance` 元数据差异会被视为等价并跳过重载。delegate 的 `role` 兜底统一为 `assistant`，避免重建空窗误闪 user 样式大气泡。消息格式渲染固定按 `format` 字段，不再按可见性动态切换 markdown/plain，避免滚动中气泡高度抖动。

Provider 返回错误（如 403）会在聊天中保留为 assistant `status=error` 气泡（红色），并随会话历史持久化，不会再因 history sync 刷新后消失。错误气泡内容会强制按 plain 渲染，避免 markdown/html 片段在实时阶段被解释后出现显示不全，并减少二次布局抖动。

会话切换采用 latest-only 单路径：每次切换只保留最新一次历史加载请求（旧请求取消并丢弃结果），历史加载固定走单次 `tail(200)` 准备后提交，不再做会话预热（prefetch）。关键路径与后台路径已分池（会话历史读写走 user IO，渠道轮询走 bg IO），以降低切换抖动。

聊天自动贴底采用非流式最小触发策略：仅在 `historyLoadingChanged(false)`（切会话完成）、`messageAppended`（assistant/system/typing 行）、`statusUpdated(done|error)`（AI 完成/报错瞬间）和用户发送瞬间触发贴底；不在 `contentUpdated` 或 `contentHeightChanged` 上连续跟随。

桌面端流式显示路径为单一路径：`gateway.py` 通过 `_progressUpdate` 逐 delta 跨线程推送到 UI，不再使用进度合并定时器（coalescing timer），减少“整块落字”体感。

未命中缓存且历史仍在加载时，聊天面板会显示显式 loading 提示，避免右侧出现长时间黑屏空窗。

侧边栏快速连点切换时，当前激活会话以“用户最新选择的 session key”为事实源，异步列表刷新不会回滚到旧会话。

会话列表刷新改为事件驱动：`statusUpdated`（消息收口）触发 `sessionService.refresh()`，不再使用独立轮询，排序更新时间与回复完成时机一致。

Session 持久化层锁已按会话 key 收敛，且 metadata 更新与历史读取锁域分离，减少 default 会话在高频切换时的偶发等待。

会话删除体验做了双收口：点击即显示成功 toast（失败由异步回包覆盖），同时 Sidebar 在重建前后恢复 `contentY`，删除后视口保持原地。`SessionItem` 点击命中也做了单一路径分区：删除按钮可见时主行点击区自动让出右侧区域，避免“选中会话”和“删除会话”争抢同一次 pointer 事件。

聊天输入区在多行场景采用单一路径高度计算：容器高度由 `contentHeight + padding + inset` 统一钳制；达到最大高度后保留底部可视安全间隙，并在光标位于末尾时自动滚动到末行，确保最后一行与光标始终可见。

输入框点击焦点仅走 `TextArea` 原生路径（移除了容器级聚焦 MouseArea），首击更稳定；文本垂直位置通过 `topPadding=6 / bottomPadding=2` 微调到 ring 视觉中心。

### 3. 使用流程

1. 打开 App → 若首次使用且未配置 Provider/Model，会自动跳转 Settings 页面；填写配置
2. 侧边栏不再提供 chat/settings 导航按钮，左下角 logo 是进入 Settings 的入口
3. 在 Settings 页面点击左侧任一会话，会直接切回 Chat 并切换到该会话
4. 网关通过侧边栏顶部网关胶囊手动启动/停止，状态与按钮在同一区域展示
5. 修改配置后点击 Save → 在网关胶囊执行重启即可应用
6. 左侧 Sidebar 的 Plan 面板会实时展示当前会话计划（目标、进度、步骤状态）；计划清空后自动收起并显示最近完成摘要
7. 在 Settings 点击“+ 添加 LLM 提供商”后，新增项会自动展开并滚动到该卡片位置，方便直接填写
8. Settings 的 Agent Defaults 新增推理强度选项：`Auto` / `off` / `low` / `medium` / `high`（保存后重启 Gateway 生效）
9. 需要查看切换性能时，可用 `BAO_DESKTOP_PROFILE=1 uv run python app/main.py` 启动，终端会输出 `History load` 相关埋点与 `history_load/history_applied` 导航日志

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
- 流式回复进行中可以切换会话；旧会话在后台继续执行，UI 隔离显示新会话内容

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

`v0.3.6` 为当前发布版本，详见 [`../CHANGELOG.md`](../CHANGELOG.md)。

完整打包指南见 [`docs/desktop-packaging.md`](../docs/desktop-packaging.md)。

补充：Desktop 后端已增加 `AsyncioRunner` 关闭收敛（先排空再取消残留任务）与 `SessionService.shutdown()` 生命周期清理，用于降低 Qt 测试批量运行时的间歇性崩溃风险。

补充：Settings 下拉字段统一走 `SettingsSelect.qml` 的自定义样式（输入框、箭头动效、弹层选项列表），避免平台默认下拉外观不一致。

> 开发细节（架构、测试命令、UI 坑点、技术要点）见 `AGENTS.md`。
