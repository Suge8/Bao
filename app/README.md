# Bao Desktop App (实验性)

基于 PySide6 + QML 的桌面客户端，**Bao 的 `bao` CLI 纯 UI 壳子**。

所有核心逻辑（AgentLoop、Channels、Cron、Heartbeat、startup greeting、首次落盘）均来自 `bao/` core，Desktop 不重复实现任何业务逻辑。启动阶段的会话浏览也已收口成单一路径：`main.py` 只发起 `SessionService.bootstrapWorkspace()`，由 asyncio 线程异步创建 `SessionManager`，再通过 `sessionManagerReady` 信号挂接到 `ChatService`；UI 线程不再同步早建会话库。`SessionManager` 本体保持轻量，LanceDB 连接与 `session_meta/session_messages` 表按职责懒打开（列会话只碰 meta，消息读写再碰 msg），索引仅在新表创建时建立；当前剩余冷启动主成本主要来自上游 `import lancedb` 的首次导入/runtime 初始化，而不是 Desktop 自身的会话装配路径。Provider SDK client 也改为首请求时再创建，因此“窗口先起来”和“首条消息前已完成 provider 校验”不再是同一件事。desktop startup 现在统一由 core 输出带语义的 startup message：onboarding 阶段发静态 assistant 消息，ready 阶段才发轻量 LLM 生成的 startup greeting；若配置了 `agents.defaults.utilityModel` 则优先使用 utility provider+model（PERSONA.md 置于 system prompt 最前面锚定语气 + CJK 本地化时间 + 原生语言 user trigger，不注入工具/技能上下文）。startup greeting 与 heartbeat 现在共用同一套 `allow_from -> normalized targets` 解析规则（Telegram 只认数字 chat_id，WhatsApp 自动补 `@s.whatsapp.net`），但投递策略保持分离：startup 使用全部合法 targets，heartbeat 只取共享 normalized target 列表中的首个合法 proactive target。这个 primary target 由渠道顺序与各渠道 `allow_from` 顺序共同决定，不是运行时“可用性探测”。desktop startup message 与外部渠道并发触发，外部渠道发送前会等待对应 channel ready；desktop 侧会先缓存消息，待目标会话已确定且该会话的历史完成加载后，再按 active 会话落库/显示，避免 startup 消息被旧 history replay 顶掉。gateway 启动成功摘要、启动失败与 channel 生命周期错误不再写入聊天历史，而是统一收口到侧边栏 gateway capsule 右侧动作区附近的 overlay bubble；这组详情由 `gatewayDetail`（文本）和 `gatewayDetailIsError`（语义）共同驱动，若启动过程中已有 channel 生命周期错误，成功摘要不会覆盖错误详情。健康摘要通过 hover 或 capsule focus disclosure 展开，错误则保持常驻可见；胶囊本体在 activeFocus 时显示明确的 focus ring，长错误会在 overlay 内限高并支持滚动查看，避免持续遮挡 session list 顶部。点击启停继续走同一个 capsule action。聊天区只保留当前会话相关的交互错误。发送成功会打印 `💬 启动问候 / out` 日志（60 字预览），轻量路径失败时回退到发送 presence 文本保底。网关需用户手动启动（点击侧边栏顶部网关胶囊），启动后桌面聊天窗口作为 `desktop` channel 与 Telegram、iMessage 等其他渠道共存运行；当前胶囊采用更高的入口高度、更宽左右留白，以及右侧核心实心圆按钮，idle / starting / running / error 四态由同一状态源驱动，其中 idle 文案为 `启动` / `Start`，idle / starting / running 三态分别使用不同图标和动效。

当前窗口外观默认使用系统标题栏；在 Windows 上会尝试调用 DWM 请求原生圆角（Windows 11 效果最佳）。主窗口默认尺寸为 `1100x720`，最小尺寸为 `640x600`，由 `Main.qml` 根窗口统一约束，避免窗口缩小到不可用状态。

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

首次运行自动创建 `~/.bao/config.jsonc`（包含 `config_version`）与默认 workspace（`~/.bao/workspace/`），无需手动初始化。若 `agents.defaults.model` 为空或 providers 中未配置 apiKey，App 自动跳转 Settings 页面引导完成配置（OpenAI 兼容端点无需额外 `apiMode` 设置；OpenAI / Anthropic / Gemini 的 `apiBase` 缺版本段会自动补齐，传入完整 endpoint 会规范回版本 base）。Settings 顶部现为 `快速开始 / 渠道 / 高级` 三段式分页：界面语言改动后即时保存，其余配置按分区小保存按钮提交，并可通过右上角 `?` 帮助按钮查看填写说明。分区保存成功后会立即恢复有效状态（`isValid=true`）；默认模板里一次补齐多个缺失配置键也会保持 JSONC 结构有效。若 JSONC patch 失败会返回可见错误（`Patch failed`），不会让界面调用崩溃。

首次 setup 现在会收敛成一条更短的新手路径：顶部欢迎卡直接把流程压缩成 `界面语言 → AI 服务 → 默认聊天 AI` 三步，不再把完整设置页一股脑甩给新用户；每一步都优先走卡片式选择，字段输入只在需要时展开。AI 服务步骤先给 `OpenAI / 官方`、`OpenRouter`、`Claude 官方`、`Gemini 官方`、`自定义兼容接口` 这些服务卡，主路径只要求补一个 API Key，连接方式与自定义接口地址都折叠到按需展开的区域；默认聊天 AI 这一步同样先给推荐卡片，手动填写准确模型名和更省钱的后台 AI 都是可选折叠项。填完默认聊天 AI 后若 setup 条件满足，会自动退出 setup 态进入聊天界面，并带一次轻量收束光晕，但不引入新的状态机或额外控制面。

聊天渲染已做收口防闪：reply finalize 后的 history refresh 仅在真正影响可见结果的字段发生变化时才会触发全量 reset。普通 user/assistant 的一次性 entrance flag 仍视为等价而跳过重载，但 system 的 `system/greeting` 持久外观差异会被正确识别并刷新。desktop 显示历史现在会保留 `format` 与 `entrance_style`，assistant 历史消息在 reload 后仍按 markdown 语义渲染，delegate 的 `role` 兜底统一为 `assistant`，避免重建空窗误闪 user 样式大气泡。消息格式渲染固定按 `format` 字段，不再按可见性动态切换 markdown/plain，避免滚动中气泡高度抖动。

聊天时间线现在也保持单一路径：消息时间仍以 `ChatMessageModel` 的 `createdAt` 为事实源，日期分隔不在 QML 侧临时回看前后消息，而是在模型侧统一产出 `dividerText` 后交给气泡 delegate 渲染。当前规则只在两种情况下显示轻量分隔线：跨天消息、以及同一天内长间隔消息；普通连续对话不额外堆时间噪音。

普通 user/assistant 气泡的文本布局也已收敛为单一路径：文本占满气泡内容区后使用统一内边距和垂直居中，不再依赖顶锚点硬撑位置；多行与单行消息的上下留白更稳定，避免出现视觉上“文字偏上”的感觉。

普通 user/assistant 气泡的入场动效现在也统一走单一路径：消息插入时直接使用既有 `entrance_style` 元数据驱动方向性滑入、轻微缩放与一次性柔光回落；user 从右侧送入、assistant 从左侧接入，不再依赖额外列表状态或补丁式计时控制。

入口动画契约也已收口为一次性路径：后端只负责在消息首次插入时提供 `entrancePending=true`，`MessageBubble` 播放后立即消费；QML 动画触发与模型 schema 都只认 `entrancePending` 这一条事实源，`entranceConsumed` 已完全删除，不再保留“把同一条消息重新打回待播放”的后门，避免模型层和 QML 层各自维护一套可重播状态。

消息点击反馈现在也统一走单一路径：普通气泡、system 与启动问候都使用气泡内部的 `overlay + ripple + progress` 驱动高光层；高光不再是额外的移动亮片，而是铺在气泡内部的同形渐变层。

ready 阶段的 AI 启动问候与系统通知仍共用同一条 system 消息链路，并由 `entrance_style` 驱动 greeting 外观；onboarding 则直接走普通 assistant 消息链路，不再复用 greeting 胶囊。历史回放会保留 `format` 与 `entrance_style`，因此 startup greeting 和普通 onboarding 消息在 reload 后都会保持各自语义。

Provider 返回错误（如 403）会在聊天中保留为 assistant `status=error` 气泡（红色），并随会话历史持久化，不会再因 history sync 刷新后消失。错误气泡内容会强制按 plain 渲染，避免 markdown/html 片段在实时阶段被解释后出现显示不全，并减少二次布局抖动。

渠道不可用、启动失败、发送失败、停止失败也会复用同一条 desktop system message 链路进入聊天区气泡，不再只停留在终端日志。

会话切换采用 latest-only 单路径：每次切换只保留最新一次历史加载请求（旧请求取消并丢弃结果），历史加载固定走单次 `tail(200)` 准备后提交，不再做会话预热（prefetch）。关键路径与后台路径已分池（会话历史读写走 user IO，渠道轮询走 bg IO），以降低切换抖动。

聊天自动贴底采用非流式最小触发策略：仅在 `historyLoadingChanged(false)`（切会话完成）、`messageAppended`（新增 user/assistant/system/greeting 行）与 `statusUpdated(done|error)`（AI 完成/报错瞬间）触发贴底；不在 `contentUpdated` 或 `contentHeightChanged` 上连续跟随。

贴底动作本身也保持单一路径：`ChatView` 在追加消息后会先对 `ListView` 做一次布局收敛，再统一执行 `positionViewAtEnd()`；像“网关已启动”这类 system 消息追加后也会稳定落到底部，不再出现信号到了但视口还停在旧位置的情况。

加载中的贴底边界也做了收口：若会话切换或 history replay 已经进入 `historyLoading=true`，前一轮排队中的 deferred follow 不会再越过当前 guard 把列表强行拉到底，避免切会话时出现旧事件把新时间线抢到底部；history fingerprint 也基于准备后的显示消息计算，不再只看最后一条原始消息。active 会话的 history replay、tool/system 插入与 transient assistant 尾泡合并规则统一收口在 `ChatMessageModel.load_prepared()`，`gateway.py` 只负责时序调度，并在 history merge 后按“尾部 assistant，若尾部还没 assistant 就补一个 typing 占位”重新附着活跃流式气泡。

桌面端流式显示路径为单一路径：`gateway.py` 通过 `_progressUpdate` 逐 delta 跨线程推送到 UI，不再使用进度合并定时器（coalescing timer），减少“整块落字”体感。应用级默认字体也会在启动时显式绑定到已存在的系统字体族，避免 Qt 回落到隐式 `Sans Serif` 别名造成额外字体初始化开销。

未命中缓存且历史仍在加载时，聊天面板会显示显式 loading 提示，避免右侧出现长时间黑屏空窗。聊天历史加载、网关启动空态与设置页更新按钮现在统一复用同一套轻量轨道式 loading 视觉，不再混用默认 `BusyIndicator`；侧边栏网关按钮则保留原有启动中动效，让等待中的观感更克制、更顺滑。

侧边栏快速连点切换时，当前激活会话以“用户最新选择的 session key”为事实源；`desktop:local` 与对应渠道 family 的 active marker 通过同一提交路径落盘，异步列表刷新不会回滚到旧会话。

会话列表刷新改为真正的提交事件驱动：`SessionManager` 在 `save/update_metadata_only/delete_session` 后统一发出变更事件，`sessionService` 只订阅这一个事件并复用 `refresh()`；不再借用 `statusUpdated` 做补偿刷新。

侧边栏“新对话”保持双入口、单动作：顶部按钮与“暂无会话”空态卡片都只触发现有的新会话动作；当列表为空时，点击空态卡片即可直接创建新会话。

侧边栏会话区也已收敛成单一路径面板：会话标题、未读汇总 badge、加号按钮与分组列表统一包在同一张会话卡片里，不再拆成“外置标题条 + 内部列表卡”两层结构。标题只保留 icon + 文本本体，AI 未读提示则沿用 `has_unread` 这一条事实源，在未读集合发生变化时对标题区做一次轻微 pulse 反馈，不引入额外轮询或补丁式 UI 状态。

会话列表右侧现在会按同一条后端数据路径显示紧凑相对时间（如 `<1m`、`5m`、`2h`、`3d`）；`SessionItem.qml` 不自行推算时间，只消费 `SessionService` 提供的 `updatedLabel`。时间标签默认保持弱化显示，hover 删除按钮时自然淡出，避免操作态和信息态相互抢位。

Session 持久化层锁已按会话 key 收敛，且 metadata 更新与历史读取锁域分离，减少 default 会话在高频切换时的偶发等待。

会话删除体验已收敛到单一路径：Sidebar 点击删除只发送意图，成功/失败 toast 统一由 `deleteCompleted` 回包决定；同时 Sidebar 在重建前后恢复 `contentY`，删除后视口保持原地。`SessionItem` 点击命中也做了单一路径分区：删除按钮可见时主行点击区自动让出右侧区域，避免“选中会话”和“删除会话”争抢同一次 pointer 事件。

chat/settings 页面切换统一写 `startView`，再由 `currentPageIndex` 绑定投影到 `StackLayout.currentIndex`；Sidebar 不再直接改 `stack.currentIndex`，避免打断绑定后形成第二条导航控制面。

聊天输入区在多行场景采用单一路径高度计算：容器高度由 `contentHeight + padding + inset` 统一钳制；达到最大高度后保留底部可视安全间隙，并在光标位于末尾时自动滚动到末行，确保最后一行与光标始终可见。

输入框点击焦点仅走 `TextArea` 原生路径（移除了容器级聚焦 MouseArea），首击更稳定；窗口层现在还补上了统一的 click-away 失焦出口：只要点击位置落在编辑器外，主窗口就会同步清掉输入选区并把焦点从编辑控件移走，避免 ring 一直保持“被选中”。同一个 `MouseButtonRelease` 边界还会补一次窗口级 pointer 重算，用来处理点击引发的切页/弹层/显隐等场景变化发生在静止鼠标下时，hover/cursor owner 不能及时刷新的问题。

输入框的视觉反馈也收敛为一条动效路径：hover/focus 时仅驱动背景、边框与极轻的缩放过渡，失焦时自然回落；文本垂直位置现在通过 `topPadding=15 / bottomPadding=5` 做非对称微调，保持当前胶囊输入框的视觉中心。

聊天 composer 的编辑层现在直接铺满输入框外壳，内部留白只由 `TextArea` 自己的 padding 决定，不再通过 `ScrollView` 再额外缩一圈；因此点击、聚焦与选中反馈会覆盖整个输入框，而不是只落在中间一小块区域。

桌面端测试现在除最小 QML harness 外，还补了一层真实页面集成回归：直接加载 `Main.qml`（从真实对象树进入 `ChatView`），在根窗口安装 `WindowFocusDismissFilter`，验证 composer 四角一次点击即可聚焦、外部点击会清焦点和选区，同时覆盖鼠标释放后会触发窗口级 pointer refresh，避免“简化 harness 通过但真实页面回归”。

发送按钮现为单一路径圆形按钮：尺寸直接复用全局 token，图标为上箭头 glyph，并在同一组件内提供轻量 hover/press 缩放；输入框与按钮都显式按垂直中心对齐，composer 的整体重心更稳定。聊天底边界也统一为单一 inset：无输入框时保留一段小底边，有输入框时消息稳定停在 composer 上方，且不能再继续向下拖出第二个边界。

### 3. 使用流程

1. 打开 App → 若首次使用且未配置 AI 服务/默认聊天 AI，会自动跳转 Settings 页面；先在三步 onboarding 里完成界面语言、AI 服务和默认聊天 AI
2. 侧边栏不再提供 chat/settings 导航按钮，左下角 logo 是进入 Settings 的入口
3. 当侧边栏暂无会话时，可直接点击空态卡片创建新会话；顶部“新对话”按钮与其语义一致
4. 在 Settings 页面点击左侧任一会话，会直接切回 Chat 并切换到该会话
5. 网关通过侧边栏顶部网关胶囊手动启动/停止；胶囊左侧展示状态 dot + 文案，右侧展示核心实心圆按钮，待启动 / 启动中 / 运行中 / 错误四态统一在同一区域反馈
6. onboarding 中界面语言会即时保存；AI 服务与默认聊天 AI 仍通过各自分区右上角按钮提交。完成后先停止再重新启动网关胶囊即可应用
7. 左侧 Sidebar 的 Plan 面板会实时展示当前会话计划（目标、进度、步骤状态）；计划清空后自动收起并显示最近完成摘要
8. 在 Settings 的常规 AI 服务配置里点击“+ 添加 LLM 提供商”后，新增项会自动展开并滚动到该卡片位置，方便直接填写
9. `回复方式与模型 / Response Setup` 分区集中管理默认聊天模型、后台模型和默认回复行为；右上角 `?` 会打开帮助说明模态
10. Settings 的 `回复方式与模型 / Response Setup` 新增推理强度选项：`Auto` / `off` / `low` / `medium` / `high`（保存后重启 Gateway 生效）
11. 需要查看切换性能时，可用 `BAO_DESKTOP_PROFILE=1 uv run python app/main.py` 启动，终端会输出 `History load` 相关埋点与 `history_load/history_applied` 导航日志
12. 左侧会话面板的未读 AI 提示会先汇总到标题区 badge；当任一会话出现新的 AI 未读时，标题区会轻微脉冲一次，切回对应会话后未读会按既有 `desktop_last_seen_ai_at < desktop_last_ai_at` 规则自动收敛

## 桌面更新

桌面端现在内置了 GitHub-native 更新链路：

- App 启动后可按 `ui.update.autoCheck` 自动静默检查更新；手动检查入口只在 Settings 的「桌面更新」区域
- 更新元数据默认读取 `ui.update.feedUrl`（默认指向 GitHub Pages 上的 `desktop-update.json`）
- macOS 更新资产使用 `Bao-x.y.z-macos-<arch>-update.zip`，下载后由 App 退出并替换当前 `.app`
- Windows 更新资产继续使用 `Bao-x.y.z-windows-x64-setup.exe`，由 App 下载后用静默参数启动安装器

Settings → `桌面更新 / Desktop Updates` 当前只保留两个用户入口：

- 自动更新开关（对应 `ui.update.autoCheck`）
- 手动 `检查` 按钮

运行时反馈也已收口：

- 未发现新版本：显示 toast `当前已是最新版本 / You're on the latest version`
- 发现新版本：弹出统一更新确认模态（与 Settings 帮助说明共用同一套 `AppModal` 行为）
- 检查失败：显示错误 toast
- `desktop-update.json` 返回 `404` 时视为“暂无更新”，不会显示失败

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

当前打包链路有两个和 CI 稳定性直接相关的约束，已内置在 `build_mac.sh` / `build_win.bat`：

- workspace 模板按 `bao.templates.workspace` package data 打包，不再把 `bao/templates/workspace` 当普通目录手工映射到 bundle 内
- Desktop 只保留 QML 所需 Qt 插件，并显式排除 `tls` 插件，避免 macOS Intel runner 把 Homebrew OpenSSL 动态库拉进 Nuitka 依赖扫描

本地打包前先同步锁定的构建依赖：`uv sync --extra desktop-build`

```bash
# macOS 本地构建
bash app/scripts/build_mac.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64
bash app/scripts/create_update_zip.sh --arch arm64

# Windows 本地构建
app\scripts\build_win.bat
app\scripts\package_win_installer.bat
```

推送 `v*` tag 自动触发 GitHub Actions 构建双平台安装包（`desktop-release.yml`）；发布 Release 后，`desktop-update-feed.yml` 会下载更新资产、生成 `desktop-update.json`，并发布到 GitHub Pages。release workflow 现已优先复用当前 GitHub-hosted Windows runner 上可用的 Inno Setup，并对已压缩安装包关闭 artifact 二次压缩；PR/非 tag push 使用轻量流水线 `desktop-ci-lite.yml` 做依赖可安装性与脚本校验。

最新桌面发布版本与变更记录详见 [`../CHANGELOG.md`](../CHANGELOG.md)。

完整打包指南见 [`docs/desktop-packaging.md`](../docs/desktop-packaging.md)。

补充：Desktop 后端已增加 `AsyncioRunner` 关闭收敛（先排空再取消残留任务）与 `SessionService.shutdown()` 生命周期清理，用于降低 Qt 测试批量运行时的间歇性崩溃风险。

补充：Settings 下拉字段统一走 `SettingsSelect.qml` 的自定义样式（输入框、箭头动效、弹层选项列表），避免平台默认下拉外观不一致；Provider、渠道与高级折叠内容统一复用 `ExpandReveal.qml`，帮助说明统一复用 `AppModal.qml`。

> 开发细节（架构、测试命令、UI 坑点、技术要点）见 `AGENTS.md`。
