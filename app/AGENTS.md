# app/ — 桌面端（PySide6 + QML）

## 🔴 最高优先设计原则（必须遵守）

- 先设计单一路径，再实现；禁止事后叠加控制修补竞态。
- 不增加状态机/定时器/分支前，先删除重复入口，保证一个事实源和一个触发点。
- 优先消除中间态可见性（避免“先到顶部再回底部”），不要靠补丁式回滚逻辑。
- 稳定性修复必须做“减控制审查”：能删则删，保留最小可用控制面。

`bao` CLI 的纯 UI 壳子。所有核心逻辑复用 `bao/` core，不重复实现业务逻辑。

## STRUCTURE

```
app/
├── main.py              # 入口：参数解析、QML 引擎、后端注入
├── backend/
│   ├── asyncio_runner.py # 独立线程 asyncio 事件循环
│   ├── chat.py          # ChatMessageModel (QAbstractListModel)
│   ├── gateway.py       # ChatService：Qt 胶水层，网关构建委托 bao/gateway/builder.py
│   ├── session.py       # SessionService + SessionListModel
│   ├── tools.py         # ToolsService：Tools 工作台 read-model + MCP 配置/探测胶水层
│   ├── config.py        # ConfigService：JSONC 读取/校验/保存（save 成功回写 isValid + patch 异常兜底）
│   └── jsonc_patch.py   # JSONC 无损 patch 写回（保留注释，新增键插入在 `}` 前）
├── qml/                 # QML UI 组件（含页面与复用组件）
└── resources/           # 静态资源（logo-circle.png / logo-bun-light.png / logo-bun-dark.png 等）
```

## WHERE TO LOOK

| 任务 | 位置 |
|------|------|
| 修改启动流程 | `main.py` — 参数解析 + QML 引擎初始化 |
| 修改聊天逻辑 | `backend/gateway.py` → 实际调用 `bao/gateway/builder.py` |
| 修改配置保存 | `backend/config.py` + `backend/jsonc_patch.py` |
| 修改 Tools 工作台 | `backend/tools.py` + `qml/ToolsWorkspace.qml` |
| 修改 UI 布局 | `qml/Main.qml`（主窗口）、`qml/ChatView.qml`、`qml/SettingsView.qml` |
| 修改侧栏品牌区 | `qml/SidebarBrandDock.qml` + `qml/Sidebar.qml` + `qml/Main.qml` strings |
| 新增 UI 文案 | `qml/Main.qml` 的 `strings` 字典（中英双语） |
| 修改安装器品牌资源 | `scripts/generate_installer_assets.py` + `scripts/create_dmg.sh` + `scripts/bao_installer.iss` |

## COMMANDS

```bash
# 桌面定向测试（本地默认）
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

# 仅在跨模块 UI/会话重构或发布前才扩大到全量
PYTHONPATH=. uv run pytest tests/ -v
```

## QML 文件清单

| 文件 | 职责 |
|------|------|
| `Main.qml` | 主窗口：系统标题栏（默认）+ 可选自绘标题栏（兼容模式）+ Sidebar + StackLayout + Design Token 单一事实源（color/typography/motion/component）+ 窗口尺寸单一事实源（默认 `1100x720` / 最小 `640x600`） |
| `Sidebar.qml` | 网关启停按钮 + 计划面板（实时目标/进度/步骤状态）+ 会话列表（i18n 分类标题）+ 左下角品牌区接入 |
| `SidebarBrandDock.qml` | 左下角品牌区：logo 设置入口 + Diagnostics 胶囊 + active 边缘描边 + idle 微动效 + hover 单气泡 |
| `PlusGlyph.qml` | 纯展示型加号图形组件，供 Sidebar 内多个“新建”视觉入口复用，避免手写几何分叉 |
| `ChatView.qml` | 消息列表 + 多状态空态引导卡片（setup/starting/error/ready/idle）+ `messageCopied()` 信号 |
| `SettingsView.qml` | 设置页主容器（顶部 tab 分页 + 分区保存 + 帮助模态入口） |
| `ToolsWorkspace.qml` | Tools 工作台：已安装能力 / MCP / 策略三段式管理界面，直接消费 core `tool_catalog` 的展示元数据（本地化名称/摘要/详情/状态/图标）+ `ToolsService` 配置/探测入口 |
| `MessageBubble.qml` | 聊天气泡（user/assistant/system）：system 走居中胶囊样式；普通 user/assistant 气泡文本通过统一内容区内边距 + 垂直居中对齐；整条消息支持点击复制（MouseArea z:10 覆盖 Text）、链接通过 linkAt() 检测后打开；点击反馈统一走内部 `overlay + ripple + progress` 高光层单路径，普通/system/启动问候均复用 |
| `SessionItem.qml` | 会话列表项（hover 删除） |
| `SettingsSection.qml` | 设置分组卡片 |
| `ChoiceCard.qml` | 统一选择卡片壳（onboarding 语言/Provider 预设/模型预设共用） |
| `OnboardingStepCard.qml` | onboarding 步骤卡壳（完成/当前/下一步状态投影 + CTA 复用） |
| `SettingsField.qml` | 文本输入字段 |
| `SettingsListField.qml` | 列表型输入字段 |
| `SettingsToggle.qml` | 开关型输入字段 |
| `ToggleSwitch.qml` | 纯展示型开关壳，状态由外层持有 |
| `SettingsSelect.qml` | 统一下拉字段（自定义 ComboBox 输入框 + Popup 列表样式 + 弹层动效） |
| `SettingsCollapsible.qml` | 可折叠设置块（复用展开动画） |
| `ExpandHeader.qml` | 可展开标题行壳（箭头/hover/点击区收口） |
| `ChannelRow.qml` | Channel 开关 + 动态字段列表（展开内容走统一 reveal 组件） |
| `ProviderCardShell.qml` | Provider 编辑卡壳（标题、类型徽标、删除入口、展开内容壳） |
| `SelectedProviderSummaryCard.qml` | onboarding 已选 Provider 摘要卡壳（标题/说明/类型徽标 + 内部表单） |
| `PillActionButton.qml` | 胶囊操作按钮壳（文案/主次态/hover 缩放统一） |
| `AsyncActionButton.qml` | 带忙碌态的操作按钮壳（spinner / disabled / hover 统一） |
| `IconCircleButton.qml` | 圆形图标按钮壳（帮助/关闭/删除/新建等入口复用） |
| `CalloutPanel.qml` | 提示/状态/hero 面板壳（onboarding 高层说明面板复用） |
| `AppToast.qml` | 全局/局部共用 toast 组件 |
| `AppModal.qml` | 统一模态框组件（帮助说明等弹层复用） |
| `ExpandReveal.qml` | 展开区域动效容器（渠道、Provider、高级项共用） |

## 技术要点

- **共享 core**：网关构建由 `bao/gateway/builder.py` + `bao/config/loader.py` 提供，Desktop 不重复实现
- **多 Channel 共存**：桌面聊天窗口作为 `desktop` channel，与其他渠道同时运行
- **线程模型**：Qt 主线程 UI + AsyncioRunner 独立线程 asyncio，agent.run() 和 channels.start_all() 作为后台 Task 并发
- **安装品牌资源单一路径**：Windows 安装器 welcome/back/small 图片与 macOS `app/resources/dmg-background.png` 必须统一由 `app/scripts/generate_installer_assets.py` 生成；`create_dmg.sh` 与 `package_win_installer.bat` 只负责在打包前刷新同一批资源，不要再分别维护两套图像或文案事实源。
- **启动期会话引导单一路径**：`SessionManager` 的早期准备由 `SessionService.bootstrapWorkspace()` 在 asyncio 线程异步创建，再通过 `sessionManagerReady` 信号交给 `ChatService.setSessionManager()`；`SessionManager` 本体保持轻量，LanceDB 连接与 `session_meta/session_messages` 表按职责懒打开（列会话只碰 meta，消息读写再碰 msg）；禁止在 `app/main.py` 的 UI 线程同步早建 `SessionManager`
- **桌面会话冷开单一路径**：会话切换的前台路径只允许“选中 session key → `ChatService` 先读内存级 snapshot（history cache / `SessionManager.peek_tail_messages()`）→ miss 时异步 `_request_history_load()`”；不要再从 Sidebar 可见项、滚动位置或其他 UI 状态主动触发批量预热，也不要在 Qt 主线程同步触库。
- **桌面会话 read-model**：`SessionManager` 维护 `session_display_tail` companion 表作为冷开首屏事实源，存 `session_key/updated_at/tail_json/message_count`；`get_tail_messages()` 在 fallback 成功后会自愈回填 companion row（含空会话 `[]`），`SessionService` 只允许在列表刷新后通过 `bg_executor` 做 legacy row backfill，不能占用用户点击会话的 user-facing user-io 路径。
- **桌面空会话摘要单一路径**：`SessionManager.list_sessions()` 负责产出 `message_count/has_messages`，`SessionService` 只做 DTO/role 透传与 `activeSummaryChanged` 发射，`ChatService` 对 known-empty session 直接进入 ready/no-messages，并静默 `_request_history_load(show_loading=False)` 一次用于 stale-summary 纠偏；不要让 QML/Sidebar 自己推断空会话。
- **LanceDB 冷启动基线**：当前 desktop 冷路径里，`SessionManager` 构造本身不触库；首次 `refresh()` 才会经 `list_sessions()` 进入 LanceDB。仓库内已将连接/开表/建索引的运行时控制面压到最小，剩余冷成本主要来自上游 `import lancedb` 与其 runtime 初始化，不要把这部分一次性外部成本误判为 app 层回归。
- **AsyncioRunner 收敛语义**：`asyncio_runner.py` 的 `start()` 通过 `loop.call_soon(_started.set)` 等待事件循环真正进入运行态，避免“已 start 但 loop 尚未 running”竞态；`shutdown()` 先排空短任务、再取消残留任务并 stop loop，降低 desktop 测试批量运行时线程残留/崩溃概率
- **Signal 跨线程**：所有 asyncio→Qt 回调通过内部 Signal 自动 marshal 到主线程
- **窗口级 click-away 失焦单路径**：编辑器是否参与窗口级 click-away blur 必须由控件显式声明（`baoClickAwayEditor`），并由 `main.py` 的 `WindowFocusDismissFilter` 作为唯一出口消费；禁止再靠类名启发式、控件类型猜测或按钮侧补丁守卫判断“是不是编辑器”。
- **下拉弹层外点收口单路径**：`SettingsSelect` 这类自带 popup 的表单控件，外部点击关闭必须优先依赖 Qt 原生 `Popup.closePolicy`；禁止再把“先关 popup，再点按钮”的补偿散落到窗口级 filter 或各个按钮里。
- **窗口级 pointer 重算**：`main.py` 的 `WindowFocusDismissFilter` 只负责 editor blur 后的 pointer 重算；启动完成与应用重新回到 active 时的首轮 hover 初始化统一走 `install_pointer_refresh_hooks()`，不要再靠额外 timer、HoverHandler 或局部补 move 事件兜底。
- **剪贴板桥接**：气泡复制通过隐藏 `TextEdit`（clipHelper，`visible: false`）的 `selectAll() → copy() → deselect()` 纯 QML 操作完成，不调用 Python slot（`clipboardService.copyText()` 在 PySide6 中从 QML 调用会触发递归溢出）
- **Diagnostics 单一路径**：桌面端 diagnostics 统一由 `bao/runtime_diagnostics.py` 收口事实源，`app/backend/diagnostics.py` 只做 QObject 投影；左下角 logo 右侧 Diagnostics 入口负责展示结构化运行诊断、日志尾部与日志目录入口，不再把控制面日志混进聊天时间线
- **Diagnostics 日志视口 owner**：`Log tail` 的文本内容继续由 `Main.qml` / `diagnosticsService.recentLogText` 提供，但滚动位置与“是否仍跟随底部”必须收口在 `FollowTailLogView.qml` 内部；父层只允许传文本/样式与在 modal 打开时显式请求一次 `followTail()`，不要把 `contentY` 或额外 follow 状态抬回页面层
- **Ask Bao 语义**：Diagnostics 面板中的“发给 Bao”仅在存在结构化诊断事件时显示，点击后会把结构化诊断摘要（+ 必要 observability 摘要）发送到当前会话，不默认附带日志尾部；“复制尾部”保持独立动作
- **Diagnostics 页面层级**：Diagnostics modal 采用扁平化 2x2 工作台（Gateway State / Log file / Recent diagnostics / Log tail）；每个 section 使用语义图标 + 单表面卡片 + 内部分隔线，不再走“卡片里套卡片”的双层结构
- **Diagnostics 关闭语义**：Diagnostics modal 只保留右上角关闭按钮，底部不再重复出现默认 `Close` action，避免双关闭入口竞争层级
- **启动消息语义**：网关启动后通过 `on_desktop_startup_message` 回调接收 core 侧 startup message（`gateway.py` 传入 lambda → `_startupMessage` Signal）；onboarding 阶段输出静态 assistant 消息，ready 阶段输出由轻量 `provider.chat` 生成的 startup greeting。ready 阶段的 desktop 与外部渠道 greeting 统一走 `assistant + entrance_style=greeting` 单一路径：desktop 目标由 `SessionService.startupTargetReady` 决定，外部渠道则在真实 `channel.send()` 成功返回后，优先按 external family 当前 active sibling（如 `telegram:chat::s2`）持久化，找不到 external family active 时再回退 natural key；desktop 当前 focus 不再参与 external routing。两者都复用同一套未读语义（`desktop_last_ai_at` / `desktop_last_seen_ai_at`）。若配置了 `agents.defaults.utilityModel` 则优先使用 utility provider+model（仅 PERSONA + 指令，不注入工具/技能上下文）；desktop 与外部渠道并发触发，外部渠道发送前会等待对应 channel ready；desktop 侧会先缓存 startup message，待目标会话已确定且该会话 history 已应用到 `ChatMessageModel` 后再落库/显示，避免 startup 消息被旧 history replay 顶掉。外部渠道真实送达后会输出 `💬 启动问候已发送 / sent` 日志；仅 fallback 到 bus 入队时才会记 `queued`，失败隔离不影响其他渠道。
- **主动消息目标解析**：startup greeting 与 heartbeat 共用同一套 `allow_from -> normalized targets` 解析规则，Telegram 仅接受数字 chat_id（支持 `-100...` 与复合字段提取），WhatsApp phone 会归一化为 `@s.whatsapp.net`；但投递策略保持分离：startup 对全部合法 target 发出，heartbeat 只消费共享 normalized target 列表中的首个合法 proactive target，维持后台单会话语义。该 primary target 由固定渠道顺序与各渠道 `allow_from` 顺序决定，不是运行时 availability 探测。
- **网关控制面详情**：gateway 启动成功摘要、启动失败和 channel 生命周期错误不再写入聊天历史；`ChatService` 统一暴露 `gatewayDetail`（文本）、`gatewayDetailIsError`（语义）与 `gatewayChannels`（结构化渠道状态）三项事实源。Sidebar 顶部通过 `GatewayStatusOrb.qml` 投影方案 B：右上角状态 pill 最多展示 2 个渠道 icon，并在超出时附加 `+N` overflow 徽标；详情 popover 统一从 pill 右侧展开，hover 胶囊、状态 pill 或详情本体时走同一条 disclosure 路径，左侧桥接 hover 区避免从 pill 进入 bubble 时闪断。浅色与深色主题分别使用独立表面色，不再共用深色分支。渠道图标资源已按渠道类型补齐（Telegram / Discord / WhatsApp / Slack / QQ / iMessage / Feishu / DingTalk / Email），并采用品牌色本地 SVG，避免退回通用 chat glyph 或单色发黑。capsule 本体在 activeFocus 时显示与设置表单一致的 focus ring，overlay 内部对长文本做统一限高并允许滚动查看；点击启停继续走 capsule 的单一路径 action，聊天区只保留当前会话相关的交互错误，避免把控制面日志混进对话时间线。
- **手动启动**：网关需用户点击侧边栏网关胶囊手动启动，不自动拉起
- **Setup 单一路径**：`Main.qml` 以 `setupMode = !configService.isValid || configService.needsSetup` 作为唯一就绪事实源；未完成配置时仅显示 `SettingsView`，并隐藏侧边栏与网关入口，避免用户进入半配置中间态
- **自动选会话**：会话 active 由 SessionManager 持久化值与当前用户选择单一路径驱动；若无 active 则在列表刷新时优先选“最新 desktop 会话”（否则按列表顺序），若一个都没有则自动新建一个 desktop 会话并设为 active，避免 UI 进入无会话中间态
- **active 可见性**：分组展开态由用户操作单一路径持有；侧栏投影只负责保证 active 会话即使在折叠分组里也仍然可见，禁止借 `activeKeyChanged` 自动重开用户手动折叠的分组
- **Sidebar 新建单动作**：顶部“新对话”按钮与“暂无会话”空态卡片保持双入口、单动作；两者都只触发同一个新会话信号，不在 Sidebar 内复制服务调用或切页语义
- **网关控件在侧边栏**：Sidebar 顶部使用更高的网关胶囊作为唯一主控入口；左侧为状态 dot + 文案，右侧为核心实心圆按钮。idle / starting / running / error 四态统一由 `chatService.state` 单一路径驱动；其中 idle / starting / running 三态各自使用不同图标与独立动效，idle 文案为 `启动` / `Start`。`handoffVisualState()`、主标题 crossfade、副标题 settle 都只是展示态投影，不得升级为第二事实源或反向驱动业务状态。
- **未启动弱化会话**：网关 idle/stopped 时会话项降透明，但仍可点击查看历史
- **会话项点击命中收敛**：`SessionItem` 采用“主行点击区 + 右侧 trailing action 保留区”双区分离；主行点击区始终为右侧操作区预留固定命中空间，不要在 hover/显隐时动态改写 pointer owner，避免左侧选中与右侧删除抢占同一次 pointer 事件
- **删除即时反馈**：会话删除先做本地乐观更新（`reset_sessions` 移除条目 + 选新 active），删 active 时优先选同 channel 的相邻会话，减少跨分组跳变；删除进行中 refresh 会过滤 pending delete，防止条目短暂复活；删除失败仅在用户未切换选择时按 snapshot 回滚。UI 点击删除只发送意图，成功/失败 toast 统一由 `deleteCompleted` 决定；本地乐观删除命中的 `deleted` 提交事件直接复用当前删除事务，不再触发第二次列表重建。若删除已落盘、只是后续 active marker 同步失败，则直接按持久化事实 refresh 收口，不把已删会话从 snapshot 回滚回来。Sidebar 的 header/session/child 最终行模型现在由 `SessionService.sidebarModel` 单一路径产出，QML 只在 projection 提交前后做一次视图锚点捕获/恢复，让删除上方会话时可见内容稳定收口，而不是自己重建列表投影。
- **侧边栏可见行单路径**：折叠分组默认只保留 header row；若 active 会话就在该分组内，则 projection 只额外保留这一条 active row。其余 session/child 行若当前不可见，应直接不进入 `SessionService.sidebarModel`，不要在 QML 中以 `height: 0`、`opacity: 0` 或类似幽灵行方式隐藏。
- **侧边栏分组展开单路径**：rail 的分组展开/收起只能由 `SessionService.sidebarModel` 驱动，并交给 `ListView` 的位移/显隐过渡完成；不要再叠加 sticky overlay、第二套 header 几何、定时器或额外分组状态。
- **SessionListModel 类型契约**：`session.py` 中 role 常量统一基于 `Qt.ItemDataRole`（`_ROLE_*`）定义，`QAbstractListModel` override 签名与 Qt stubs 对齐（`rowCount`/`data` 支持 `QModelIndex | QPersistentModelIndex`，`roleNames` 返回 `dict[int, QByteArray]`），避免 basedpyright 的 Qt 属性与 override 噪音诊断
- **SessionService 生命周期清理**：`SessionService.shutdown()` 仅做 disposed 标记与运行态清理（pending select/delete + session_manager 释放）；所有 runner 提交路径走 `_submit_safe()`，在 runner 已停止时吞掉 `RuntimeError` 并关闭未提交协程，避免尾调用访问已停 runner 的竞态
- **会话切换单一路径**：`SessionService._handle_list_result()` 在存在 `_pending_select_key` 时优先采用该 key 作为 active，避免“快速连点切换 + list 回包滞后”把用户最新选择覆盖回旧会话；保持 active 事实源由当前选择驱动，列表刷新只做数据同步
- **页面导航单一路径**：`Main.qml` 的 chat/settings 切换统一写 `root.startView`，由 `currentPageIndex` 绑定投影到 `StackLayout.currentIndex`；禁止从 Sidebar 或其他子组件直接写 `stack.currentIndex` 破坏绑定。
- **侧栏选中态单一路径**：Sidebar 的应用级选中目标统一由 `Main.qml` 派生并下发；聊天页沿用当前 workspace，会话高亮只在 chat 页投影，Settings 显示时左下角 logo 拥有唯一选中态，禁止让上一条 session/workspace 继续保留全局选中表现。
- **删除反馈单一路径**：会话删除结果只由 `sessionService.deleteCompleted` 决定；UI 点击删除只发意图，不得先行 toast “成功” 再靠失败回滚覆盖。
- **跨渠道 active 边界**：Desktop 当前选择只维护 `desktop:local` 这条视图 active；external family active 由 core 渠道路由自己维护（如 `/new`、`/session` 等显式 external flow），Desktop 浏览 external sibling 不再反向改写 external family marker，避免 UI 状态污染 startup / proactive routing。
- **会话列表刷新触发**：SessionService 不再独立轮询，也不再借用 `statusUpdated` 做补偿刷新；唯一触发点改为 `SessionManager` 提交事件（`save/update_metadata_only/delete_session`），Desktop 仅订阅提交并复用 `refresh()`，让排序与 unread 更新都跟随持久化事实源。
- **新消息红点**：`SessionItem` 未读红点只基于 AI 时间戳单一路径：`desktop_last_ai_at`（assistant 消息写入时更新）与 `desktop_last_seen_ai_at`（用户切换到该会话时更新）比较；`hasUnread = desktop_last_seen_ai_at < desktop_last_ai_at`。不再使用 `updated_at`、不做模型层 `clear_unread`、不做 `_handle_list_result` 合并补丁，也不在 QML 侧做乐观清除；active 会话在结果组装时直接置 `has_unread=false`。
- **统一气泡提示**：`AppToast.qml` 作为可复用实心 toast 组件，Main/Settings 共用
- **多状态空态**：ChatView 根据 needsSetup/starting/error/running/idle 显示不同引导卡片
- **自动贴底收敛（非流式）**：`ChatView` 仅在 4 类瞬时事件触发贴底：`sessionViewApplied`（后端已把 switched-session 的本地 snapshot/clear 应用到视图）、`historyLoadingChanged(false)`（authoritative full history 完成对齐）、`messageAppended`（新增 user/assistant/system/greeting 行）、`statusUpdated(done|error)`（AI 完成/报错瞬间）。贴底请求统一收口到 `queuePinnedReconcile()` 的单一 `pendingPinnedReconcile` 对象，不再拆成多位排队状态；真正的目标始终只有当前 bottom（`originY + contentHeight - height`）
- **聊天页键盘滚动单一路径**：`ChatView` 的 `ListView` 是聊天页键盘滚动唯一 owner；输入框未聚焦时，`Up/Down/PageUp/PageDown/Home/End` 统一经 `Keys.onPressed` 进入 `scrollBy()/positionViewAtBeginning()/positionViewAtEnd()`，边界按 `originY + contentHeight - height` 语义计算，禁止再用裸 `Shortcut` 或手写 `0..contentHeight-height` 坐标系
- **同会话 reset 视口恢复**：`ChatView` 只在 `messageList.model` 的同会话 `modelReset` 路径恢复旧视口；切会话后的默认贴底由 `ChatService.sessionViewApplied`（本地 snapshot/clear 已应用）与 history/model reset 事件驱动，QML 不直接把 `SessionService.activeKeyChanged` 当滚动触发器
- **标题栏单一路径**：桌面窗口默认保留系统标题栏语义；macOS 允许通过 `ExpandedClientAreaHint + NoTitleBarBackgroundHint` 扩展到透明标题区，但聊天内容必须统一吃 `windowContentInsetTop`，不要再在页面内猜测 traffic lights 安全区
- **聊天布局单一路径**：`ChatView` 采用 `ListView` 铺底 + floating composer 覆盖层结构；顶部边界由 `windowContentInsetTop + 内容间距` 收口，底部边界由单一 inset 语义收口（`targetListBottomInset` 为几何事实源，`presentedListBottomInset` 仅为动画投影；idle 时为底部留白，running 时为 composer 高度 + 底边距 + 顶部停靠间隙），禁止回退到“列表在上、输入栏顺排在下”或“视口让位/内容尾白双重建模”的双路径布局
- **输入框末行可见性**：`ChatView` 输入区高度统一按 `contentHeight + padding + inset` 钳制到 `[min,max]`，到达上限后保留底部 safe gap，并在光标位于文本末尾时将 `ScrollView` 对齐到末行，避免“最后一行/光标被底边裁切”
- **输入框首击/悬浮单路径**：输入区移除容器级聚焦 `MouseArea`，点击焦点与 hover 均由 `TextArea` 原生路径处理，避免“首击偶发无效/二次点击才生效”的事件竞争，以及 hover owner 分裂。
- **Settings 首击契约**：Settings 内的 tab、Provider 展开头、`+ 添加 LLM 提供商` 等点击入口必须保留自己的 click owner；窗口级失焦只能在同次点击完成后收口，不得吞掉首击或要求第二次点击才能生效。
- **输入框视觉对齐**：`TextArea` 采用非对称微调内边距（`topPadding=15`、`bottomPadding=5`）以匹配当前胶囊输入框的视觉中心。
- **composer 纵向对齐**：输入框容器与发送按钮都显式使用 `Layout.alignment: Qt.AlignVCenter`，避免依赖布局默认值造成输入区与按钮视觉中心漂移。
- **发送按钮单一路径**：发送按钮使用 `sizeButton` 驱动的真圆形几何，图标固定走 `resources/icons/send.svg` 的上箭头 glyph；交互反馈仅在按钮组件内做 hover/press 缩放、柔光和高光层，不新增额外状态机。
- **错误可见**：网关初始化失败和 channel 生命周期错误统一进入 gateway capsule detail bubble；ChatView 空态在 `state=error` 时仍直接读取 `lastError`，让用户能在主区看到失败原因并重试
- **渠道错误可见**：渠道不可用、启动失败、发送失败、停止失败统一通过 `ChannelManager` 的单一错误出口上送 Desktop，并更新 `ChatService.lastError/gatewayDetail`；不要在 UI 层解析日志或额外造第二套错误提示通道
- **Provider 错误可见且可追溯**：provider 返回错误会保留为 assistant `status=error` 消息并在气泡层显示红色；错误气泡在实时阶段强制使用 `plain` 渲染（不走 markdown），避免 `Error calling ...` 文本内的 markdown/html 片段导致显示不全；history refresh 后保持一致
- **流式渲染**：通过 `gateway.py` 的 `_progressUpdate` 信号把 provider 的增量 token 逐 delta 跨线程推送到 UI（无 progress coalescing timer，非 `QTimer` 模拟）
- **跨渠道实时同步**：`SessionManager` 在消息提交、metadata 更新、删除后统一发出提交事件；`gateway.py` 仅在“当前激活会话收到 messages 提交”时触发一次无 loading 的 history reload，`session.py` 统一走 `refresh()` 更新侧栏。Desktop 不再依赖定时拉取或 UI 状态信号猜变化，保持“session 持久化为事实源、提交事件为唯一触发点”；其中 active desktop 会话的成功收尾必须走 `SessionManager` 单次完成路径，先清 `session_running` runtime overlay，再提交 `desktop_last_seen_ai_at` 的 metadata refresh，禁止拆成两次相互竞争的 UI 可见更新。
- **finalize 防闪烁收口**：`chat.py` 的 `load_prepared()` 统一负责渲染等价跳过、同长度增量更新，以及 active 会话下 tool/system 插入后的 transient assistant 尾泡合并，避免 history refresh 触发 `beginResetModel()` 导致气泡瞬闪或列表跳顶；`gateway.py` 只保留时序调度，并在 history merge 后按“尾部 assistant，若尾部还没 assistant 则补 typing 占位”重新附着活跃流式气泡，不直接判断 model 私有结构；`ChatView.qml` delegate 与 `MessageBubble.qml` 默认 `role` 兜底统一为 `assistant`，杜绝重建空窗误闪 user 大气泡
- **多轮分泡防抖**：Agent loop 多迭代边界通过 `providers/retry.py` 的 `PROGRESS_RESET`（当前值 `"\x00"`）标记，UI 在下一段真实增量到达时再切新气泡，避免内容“先出现在上一泡再跳走”与空白 done 泡
- **工具执行可视反馈**：`gateway.py` 订阅 `process_direct(..., on_event=...)` 的 `TOOL_HINT` 事件；当当前气泡已有文本时会收口并新建空 `typing` 气泡，确保长工具执行阶段底部持续显示三点动画
- **配置保存稳态**：`config.py` 的 `save()` 成功后会将 `_valid` 置回 `true` 并触发 `stateChanged`；写盘通过原子替换 helper 统一收口，`patch_jsonc` 异常统一转为 `saveError("Patch failed: ...")`，避免 QML 调用保存时异常冒泡
- **JSONC 无损写回**：tokenizer-based parser 记录字节区间，patch 从右往左应用；对象新增键统一插入在 `}` 前，避免尾部注释从旧键“漂移”到新键后
- **设置页信息架构**：`SettingsView.qml` 采用 `快速开始 / 渠道 / 高级` 顶部 tab 分页；桌面端专属的界面语言/主题走本地偏好即时保存，其余运行时配置按分区小保存按钮提交，避免“有的自动存、有的整页存”的混合语义
- **onboarding 完成条件单一路径**：最后一步“保存并开始聊天”按钮同时依赖 `providerConfigured` 与当前 `onboardingDraftModel` 非空；按钮可用态必须和用户眼里的真实完成条件一致，不能只看已保存 provider 状态
- **字段保存语义收口**：`SettingsToggle.qml`、`SettingsSelect.qml` 与 `ChannelRow.qml` 内的 enabled 开关统一遵循“配置里已有真实值，或用户本轮确实改过，才参与 `collectFields()` 保存”；缺值字段不会因为控件默认首项/默认关态被静默写回
- **帮助说明单路径**：提供商、渠道、回复方式与模型的说明弹层统一走 `AppModal.qml`；设置页不再各自手写遮罩/关闭逻辑
- **更新确认单路径**：桌面更新发现新版本后的确认弹层也复用 `AppModal.qml`，保证 Esc / 外部点击关闭 / 高度约束 / 滚动行为一致
- **展开动效单路径**：Provider 卡片、渠道详情与高级折叠块统一走 `ExpandReveal.qml`，箭头旋转与内容 reveal 分离，避免每个组件各写一套展开控制
- **桌面复用壳层单路径**：选择卡片、胶囊按钮、圆形图标按钮、开关、展开标题行、提示面板分别收口到 `ChoiceCard.qml`、`PillActionButton.qml`、`IconCircleButton.qml`、`ToggleSwitch.qml`、`ExpandHeader.qml`、`CalloutPanel.qml`；这些组件只负责展示和交互壳，不持有业务配置状态
- **Tools 工作台单一路径**：内建工具目录由 core `bao/agent/tool_catalog.py` 提供，Desktop 侧只通过 `backend/tools.py` 做 read-model、配置写回与 MCP probe 胶水，`qml/ToolsWorkspace.qml` 只负责投影/筛选/交互，不重复实现业务逻辑或维护第二套工具状态源
- **Tools 工作台展示事实源**：builtin 与 MCP item 的本地化名称、摘要、详情、状态说明和图标都由 `tool_catalog.py` 一次产出；QML 只允许做 `localizedText()` fallback，不再按 builtin id 维护文案/图标映射函数
- **设置页壳层继续收口**：onboarding 步骤卡、Provider 编辑卡、已选 Provider 摘要卡分别收口到 `OnboardingStepCard.qml`、`ProviderCardShell.qml`、`SelectedProviderSummaryCard.qml`；`expanded`、字段引用与 `collectFields()` 保存路径仍留在 `SettingsView.qml`，组件只承接展示与插槽布局
- **Provider 保存语义**：设置页对 provider 名称做唯一性校验，并始终以完整 `providers` 对象作为唯一写回路径；新增、重命名、带 `.` 名称与字段编辑都走同一条保存语义，避免 dotpath 歧义与旧键残留
- **Provider 数据保真**：整块写回前会以 `configService.getValue("providers")` 的原 provider 对象为基底合并，保留 UI 未暴露的自定义字段（再覆盖 type/apiKey/apiBase 编辑值）
- **Provider 高级字段隐藏**：`extraHeaders` 仍保留在运行时配置里，但设置页默认不展示；保存时会继续保留原对象上的这类未暴露字段
- **OpenAI-family 生成参数**：Settings 的 Agent Defaults 区统一暴露 `reasoningEffort` 与 `serviceTier`；`serviceTier` 必须用用户友好的下拉（默认 / 极速优先 / 省钱优先）映射到 `null / priority / flex`，不再暴露模糊的 fastmode 文案
- **Provider 新增交互**：点击“+ 添加 LLM 提供商”后仅通过 `_providerList` 驱动 delegate 创建；`_pendingExpandProviderName` 必须先于 `_providerList` 更新写入，让新卡片在 `Component.onCompleted` 中一次性完成自展开与滚动，禁止额外 `itemAt()`/重试式补路径
- **Provider 顺序单一路径**：设置页 provider 列表直接使用 `providers` 对象的出现顺序；Desktop 不再持久化额外 `order` 字段，减少仅为 UI 排序存在的配置噪音
- **Provider 注释模板补齐**：`config.py` 在整块写回 `providers` 后会补一段最小示例注释（`apiBase/apiKey/extraHeaders/type`），让空 `providers` 区块在 JSONC 中仍然可自解释
- **配置对齐原则**：Settings 页面优先暴露常用且必要的配置；像 `extraHeaders` 这类低频高级字段保留在 JSONC 中手动编辑，不强行塞进表单
- **推理强度设置对齐**：Settings 的 `Response Setup / 回复方式与模型` 提供 `reasoningEffort` 枚举（`Auto/off/low/medium/high`），`Auto` 保存为 `null`，其余值按原样写入 `agents.defaults.reasoningEffort`
- **UI 样式稳定**：启动时强制 `Qt Quick Controls = Basic` + 禁用 QML 磁盘缓存
- **Design Token 分层**：`Main.qml` 统一维护 foundation → semantic → component 三层 token；组件不得新增动画/交互时序魔法值（duration/velocity/easing/幅度）
- **窗口尺寸收口**：`Main.qml` 根窗口统一定义默认尺寸 `1100x720` 与最小尺寸 `640x600`；不要把最小尺寸约束分散到多个子组件里打补丁
- **动效统一收敛**：全量 QML 动效统一走 `motion*` 与 `ease*` token（含 toast 停留时长、stagger、状态脉冲、跟随速度）；保留 `MessageBubble.qml` 的 `interval: 0` 作为事件循环调度，不视为视觉动效时长
- **丝滑实现约束**：优先动画 `opacity/scale/rotation/translate`；开关滑块跟随采用 `SmoothedAnimation`；避免新增 `Behavior on y` 和不必要的布局抖动路径
- **输入选区主题化**：输入框/文本域统一设置 `selectionColor` 与 `selectedTextColor`，禁止回退系统默认蓝色选区
- **切页布局稳定**：Chat/Settings 在 `StackLayout` 中按页动态加载，规避切回 Settings 后输入框宽度塌陷
- **Provider 延迟加载**：`bao.providers` 按需 import，缺依赖不崩
- **侧边栏分类 i18n**：会话分组标题通过 `strings["channel_" + key]` 动态本地化，支持中英切换
- **计划/定时任务/心跳投影**：Plan 状态写入 `Session.metadata`（`_plan_state/_plan_archived`），cron/heartbeat 写入各自 session；Desktop 不再维护独立投影状态源，统一依赖 `SessionManager` 提交事件触发 session refresh / history reload。
- **计划面板动效**：Sidebar 计划卡片包含状态色过渡、脉冲和步骤错峰入场动画；`clip: true` 防止过渡溢出
- **Heartbeat 独立分组**：heartbeat 会话从 system 中独立，排序固定在最底部（desktop 固定最顶部）
- **Sidebar Brand Dock**：左下角品牌区采用 `SidebarBrandDock.qml` 单一路径；logo 使用 `logo-bun-light.png` / `logo-bun-dark.png`，active 只允许边缘描边，禁止回退整块圆底或外围光环
- **设置页会话直切聊天**：在 settings 页面点击左侧会话会直接切回 chat 并加载目标会话历史
- **悬浮气泡**：hover logo 时只允许单一扁平气泡；文案来自 `Main.qml` 的 `bubble_0`~`bubble_4`，跟随界面语言，禁止尾巴、多层渐变和额外装饰
- **窗口标题清空**：`Main.qml` title 为空字符串，不显示 "bao" 文字
- **系统消息渲染**：`chat.py` 的 `load_history` 通过 `_source` 元数据区分可见系统消息（如 `cron/heartbeat/desktop-system`），有 `_source` 的 user 消息渲染为 system 胶囊；`prepare_history` 会透传合法 `status`（typing/done/error）与合法 `entrance_style`（`system/greeting`）供气泡样式使用。子代理完成态不再走可见 system 气泡路径，而是以内部 `ControlEvent(kind=subagent_result)` 交给父代理整理，再只把父代理整理后的 assistant 回复写入时间线；旧 `metadata.system_event/control_event` 仅保留兼容入口。startup message 在 `gateway.py` 先按语义分流：onboarding 直接走 assistant，ready greeting 与错误/状态提示走 system。通知路由继续优先使用 `metadata.session_key`，避免切会话时写错时间线；网关启动/错误类本地 system 提示会直接写入当前 session 历史（`role=system, _source=desktop-system`），history refresh 后保持原时间线位置不漂移
- **启动消息队列契约**：`gateway.py` 的 `_startup_pending` 与 `_pending_notifications` 统一缓存 `_QueuedUiMessage`，以 `role/content/session_key/status/entrance_style` 作为唯一消息事实源；drain 时按 `session_key` 落到对应消息链路，跨会话 startup/notification 不再误插当前时间线
- **系统胶囊动效**：system 消息支持可见入场动画（淡入 + 位移回弹）与柔光脉冲（near aura，error 额外带 far aura），光晕为一次性脉冲后回落至 0，避免常驻霓虹感；ready 阶段 startup greeting 虽然持久化为 assistant，但只要 `entrance_style=greeting` 就继续走 greeting 外观，并在 `MessageBubble.qml` 中以 full-round pill + `ignite.svg` 图标呈现；普通 system 与 error system 保持紧凑胶囊并使用不同色阶；onboarding 不复用 greeting 胶囊。`MessageBubble.qml` 的 entrance/content morph/pending surface 统一经 profile helper 派生，profile fallback 必须保持一致，避免不同动效面持有各自的状态语义。
- **消息格式契约生效**：`ChatView` delegate 会把 `model.format` 传给 `MessageBubble`；`MessageBubble` 按 `format` 在 `MarkdownText` 与 `PlainText` 间切换，避免 plain 文本被误按 markdown 解析
- **消息渲染稳定优先**：`MessageBubble` 不再基于可见性动态切换 markdown/plain，避免滚动过程中 delegate 高度波动导致滚动条抖动
- **气泡点击复制**：`MessageBubble` 用 `Text`（`MarkdownText`，纯展示无鼠标处理）+ `MouseArea`（z:10 覆盖 Text），不支持文本选择，user/assistant/system/启动问候整条消息点击即复制；链接通过 `contentText.linkAt()` 检测，命中则打开浏览器而非复制
- **气泡交互分层**：`MouseArea`（z:10，覆盖 Text，统一持有 hover/cursor/click，linkAt() 检测链接）+ `Text`（纯展示，不处理鼠标事件）。MouseArea 在最高层确保 MarkdownText 内部 QTextDocument 不会收到 press 事件，从根源杜绝 markdown re-layout 导致的 delegate 高度瞬变
- **点击防抖动**：气泡 `MouseArea` 启用 `preventStealing: true` + `z: 10`（高于 Text），双重防护：(1) 阻止父级 `ListView` 抢占拖拽 (2) 阻止 `Text(MarkdownText)` 内部 QTextDocument 收到 press 触发 re-layout，从根源消除点击时 delegate 高度瞬变引发的列表抖动
- **点击复制**：点击反馈统一走 `copyCurrentMessage()` 单入口；通过隐藏 `TextEdit`（clipHelper）的 `selectAll() → copy() → deselect()` 纯 QML 写剪贴板（不调用 Python `clipboardService`，避免 PySide6 递归溢出）+ `messageCopied()` signal → `Main.qml` 的 `globalToast` 显示「已复制」；普通气泡、system 与启动问候统一使用内部 `overlay + ripple + progress` 高光层，不再额外叠加独立 click aura；点击链接则打开浏览器，不触发复制
- **Pointer 契约**：Desktop 全部交互入口统一由实际命中的 `MouseArea` 持有 `hoverEnabled + cursorShape + onClicked`；允许全覆盖 `MouseArea` 作为唯一 pointer owner，但避免 `HoverHandler`、底层控件或额外覆盖层分拆 hover/cursor/click ownership。
- **气泡高度计算**：普通气泡使用 `contentText.contentHeight + bubblePaddingTop + bubblePaddingBottom`，system 胶囊使用 `systemText.contentHeight + 14`（均非 `implicitHeight`），`contentHeight` 对 Text 换行后的真实文档高度更可靠
- **气泡宽度单向约束**：`MessageBubble` 使用固定上限宽度测量文本（`contentMeasure/systemMeasure`）后再回填气泡宽度，避免 `implicitWidth` 反向驱动布局引发偶发超长与重排闪烁
- **普通气泡文本垂直居中**：`MessageBubble` 的普通消息文本同时锚定到内容区上下边，并通过统一 padding + `verticalAlignment: Text.AlignVCenter` 保持单行/多行时的上下留白稳定；不要回退到只设 `topMargin` 的顶锚方案

## ANTI-PATTERNS

- **禁止裸英文常量** → 走 `strings` 字典或 `tr(zh, en)`
- 不要用 `t("...")` 函数式读取 → 绑定不刷新
- 桌面端界面语言/主题属于本地 UI 偏好 → 走 `desktopPreferences` + `QSettings`，不要回写共享 runtime config
- Python 侧负责把 `desktopPreferences.effectiveLanguage` 同步给 `ChatService`；QML 只消费语言投影，不要再增加第二条语言同步入口
- 不要用 `setMask()` 做圆角；需要平台圆角时优先走系统 API（如 Windows DWM）
- QML 颜色格式是 `#AARRGGBB`（不是 `#RRGGBBAA`）

## UI 坑点

- `--smoke-screenshot <path>` 是"截图后自动退出"模式，窗口闪一下就结束是预期行为，不是崩溃
- 系统标题栏模式下，圆角优先依赖系统窗口能力（Windows 11 可用 DWM 圆角偏好）
- 顶部圆角锯齿/台阶 → 检查是否多层重复绘制标题栏背景。当前 `titleBar` 用 `Item`（不额外上色）避免双层边缘
- 语言切换必须走 `Main.qml` 的响应式 `strings` 字典，不要新增 `t("...")` 函数式读取
- 桌面端界面语言/主题持久化走 `QSettings`，不要写 `ui.language` 或其他共享 runtime config 字段
- `desktopPreferences` 是桌面语言/主题的唯一事实源，不要再创建 `themeManager` 之类的别名 context property
- 兼容旧 `ui.language` 时，启动阶段就要迁移到 `desktopPreferences/QSettings`，不要继续依赖共享 config 中的 legacy 字段存活
- 自动语言识别走 Python 侧 `detect_system_ui_language()`（`QLocale` + macOS `AppleLanguages` 兜底），QML 只消费 `systemUiLanguage`
- Settings 页本地化：公共壳层走 `Main.qml` 的 `strings`，字段级走 `SettingsView.qml` 的 `tr(zh, en)`
- Provider 改名属于整块写回路径：会避免“改名后多一条”问题，但 `providers` 节点内注释/手工排版可能被重排
- QML 颜色格式是 `#AARRGGBB`（不是 `#RRGGBBAA`），如 `#08FFFFFF` = 3% 透明白色
- App Icon 使用预裁剪圆形 PNG（`logo-circle.png`），不要用 QML Canvas 裁剪 → 避免锯齿/像素感
- Icon 光环（glowRing）必须作为 appIconBtn 的兄弟元素，不能放在 appIconBtn 内部 → 否则被 clip 裁掉
- 悬浮气泡的 `bubbleText.text` 在 `onEntered` 中赋值，`speechBubble.show` 控制显隐，`onExited` 重置
- 气泡交互层级：`MouseArea`（z:10，最高层，接管所有点击）覆盖 `Text`（纯展示，不处理鼠标）。链接检测走 `contentText.linkAt(x,y)` 而非 `onLinkActivated`，避免 MarkdownText 内部 QTextDocument 收到 press 触发 re-layout。不要用 `TapHandler` 替代 — 它会在点击链接时也触发复制
- 气泡内不要用可见 `TextEdit` 做内容展示 — 会启用文本选择，与整体点击复制冲突。用 `Text`（`MarkdownText`）纯展示即可。隐藏 `TextEdit`（clipHelper，`visible: false`）仅作剪贴板辅助，不影响交互。不要给 Text 加 `onLinkActivated`（会让 QTextDocument 处理鼠标事件导致 re-layout 抖动）
- 气泡 toast 通知走 signal 链路（`MessageBubble.toastFunc()` → `ChatView.messageCopied()` → `Main.qml onMessageCopied`），不要在 delegate 闭包里直接引用 `Main.qml` 的 id
- `ChatView.qml` 与 `MessageBubble.qml` 的 `role` fallback 不要回退到 `"user"`，否则在 delegate 重建/绑定空窗会出现 user 样式误闪
