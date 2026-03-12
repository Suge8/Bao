# Bao Desktop App

基于 PySide6 + QML 的桌面客户端，是 **Bao 的主入口产品形态**。

大多数用户应直接从 GitHub Release 下载桌面安装包；本页主要面向仓库内本地运行、开发和打包维护。所有核心逻辑（AgentLoop、Channels、Cron、Heartbeat、startup greeting、首次落盘）均来自 `bao/` core，Desktop 不重复实现任何业务逻辑。启动阶段的会话浏览也已收口成单一路径：`main.py` 只发起 `SessionService.bootstrapWorkspace()`，由 asyncio 线程异步创建 `SessionManager`，再通过 `sessionManagerReady` 信号挂接到 `ChatService`；UI 线程不再同步早建会话库。`SessionManager` 本体保持轻量，LanceDB 连接与 `session_meta/session_messages` 表按职责懒打开（列会话只碰 meta，消息读写再碰 msg），索引仅在新表创建时建立；当前剩余冷启动主成本主要来自上游 `import lancedb` 的首次导入/runtime 初始化，而不是 Desktop 自身的会话装配路径。Provider SDK client 也改为首请求时再创建，因此“窗口先起来”和“首条消息前已完成 provider 校验”不再是同一件事。desktop startup 现在统一由 core 输出带语义的 startup message：onboarding 阶段发静态 assistant 消息，ready 阶段才发轻量 LLM 生成的 startup greeting；若配置了 `agents.defaults.utilityModel` 则优先使用 utility provider+model（PERSONA.md 置于 system prompt 最前面锚定语气 + CJK 本地化时间 + 原生语言 user trigger，不注入工具/技能上下文）。startup greeting 与 heartbeat 现在共用同一套 `allow_from -> normalized targets` 解析规则（Telegram 只认数字 chat_id，WhatsApp 自动补 `@s.whatsapp.net`），但投递策略保持分离：startup 使用全部合法 targets，heartbeat 只取共享 normalized target 列表中的首个合法 proactive target。这个 primary target 由渠道顺序与各渠道 `allow_from` 顺序共同决定，不是运行时“可用性探测”。desktop startup message 与外部渠道并发触发，外部渠道发送前会等待对应 channel ready；desktop 侧会先缓存消息，待目标会话已确定且该会话的历史完成加载后，再按 active 会话落库/显示，避免 startup 消息被旧 history replay 顶掉。gateway 控制面现在进一步收口为结构化渠道状态投影：`ChatService` 暴露 `gatewayDetail`、`gatewayDetailIsError` 与 `gatewayChannels`，`Sidebar` 通过 `GatewayStatusOrb.qml` 以方案 B 呈现右上角状态 pill。状态 pill 最多显示 2 个渠道 icon，并在超出时显示 `+N` 徽标；popover 宽度按内容自适应，而不再固定大面板。hover 胶囊、状态 pill 或详情本体时，pill 锚定的详情 popover 会从右侧展开，并通过左侧 hover bridge 保持进入浮层时不断开。若启动过程中已有 channel 生命周期错误，成功摘要不会覆盖错误详情；长错误会在 overlay 内限高并支持滚动查看，避免持续遮挡 session list 顶部。浅色与深色主题分别使用独立表面色，渠道图标资源已补齐为真实/品牌近似的本地 SVG（Telegram / Discord / WhatsApp / Slack / QQ / iMessage / Feishu / DingTalk / Email），并保留品牌色，不再退回通用 chat icon 或单色发黑。点击启停继续走同一个 capsule action。聊天区只保留当前会话相关的交互错误。发送成功会打印 `💬 启动问候 / out` 日志（60 字预览），轻量路径失败时回退到发送 presence 文本保底。网关需用户手动启动（点击侧边栏顶部网关胶囊），启动后桌面聊天窗口作为 `desktop` channel 与 Telegram、iMessage 等其他渠道共存运行；当前胶囊采用更高的入口高度、更宽左右留白，以及右侧核心实心圆按钮，idle / starting / running / error 四态由同一状态源驱动，其中 idle / starting / running 三态各自复用 `gatewayChannels` 形成的不同 orb/status 呈现。

当前窗口外观默认使用系统标题栏；在 Windows 上会尝试调用 DWM 请求原生圆角（Windows 11 效果最佳）。主窗口默认尺寸为 `1100x720`，最小尺寸为 `640x600`，由 `Main.qml` 根窗口统一约束，避免窗口缩小到不可用状态。

## 快速开始

如果你是普通用户，请直接下载 Release 安装包；如果你正在仓库里工作，按下面步骤本地启动桌面端。

### 1. 安装依赖

```bash
uv sync --extra desktop
```

### 2. 启动应用

```bash
uv run python app/main.py
```

首次运行自动创建 `~/.bao/config.jsonc`（包含 `config_version`）与默认 workspace（`~/.bao/workspace/`），无需手动初始化。若 `agents.defaults.model` 为空或 providers 中未配置 apiKey，App 自动跳转 Settings 页面引导完成配置（OpenAI 兼容端点无需额外 `apiMode` 设置；OpenAI / Anthropic / Gemini 的 `apiBase` 缺版本段会自动补齐，传入完整 endpoint 会规范回版本 base）。Settings 顶部现为 `快速开始 / 渠道 / 高级` 三段式分页：桌面端专属的界面语言与主题会即时保存到本地偏好（跟共享 runtime config 分离），并由 `desktopPreferences` 作为唯一事实源同步到 UI 与 `ChatService`；旧配置里的 `ui.language` 会在首次启动时迁移进本地偏好，避免后续保存桌面更新设置时丢失原语言。其余配置按分区小保存按钮提交，并可通过右上角 `?` 帮助按钮查看填写说明。分区保存成功后会立即恢复有效状态（`isValid=true`）；默认模板里一次补齐多个缺失配置键也会保持 JSONC 结构有效。若 JSONC patch 失败会返回可见错误（`Patch failed`），不会让界面调用崩溃。

首次 setup 现在会收敛成一条更短的新手路径：顶部欢迎卡直接把流程压缩成 `界面语言 → AI 服务 → 默认聊天 AI` 三步，不再把完整设置页一股脑甩给新用户；每一步都优先走卡片式选择，字段输入只在需要时展开。setup 页顶部留白也不再自己补魔法数，而是和聊天页共用 `windowContentInsetTop/Side/Bottom` 这一套窗口安全区事实源，避免 macOS 透明标题栏、Windows 标题区与 onboarding 内容互相遮挡。AI 服务步骤先给 `OpenAI / 官方`、`OpenRouter`、`Claude 官方`、`Gemini 官方`、`自定义兼容接口` 这些服务卡，主路径只要求补一个 API Key，连接方式与自定义接口地址都折叠到按需展开的区域；默认聊天 AI 这一步同样先给推荐卡片，手动填写准确模型名和更省钱的后台 AI 都是可选折叠项。填完默认聊天 AI 后若 setup 条件满足，会自动退出 setup 态进入聊天界面，并带一次轻量收束光晕，但不引入新的状态机或额外控制面。

聊天渲染已做收口防闪：reply finalize 后的 history refresh 仅在真正影响可见结果的字段发生变化时才会触发全量 reset。普通 user/assistant 的一次性 entrance flag 仍视为等价而跳过重载，但 system 的 `system/greeting` 持久外观差异会被正确识别并刷新。desktop 显示历史现在会保留 `format` 与 `entrance_style`，assistant 历史消息在 reload 后仍按 markdown 语义渲染，delegate 的 `role` 兜底统一为 `assistant`，避免重建空窗误闪 user 样式大气泡。消息格式渲染固定按 `format` 字段，不再按可见性动态切换 markdown/plain，避免滚动中气泡高度抖动。

发送路径现在也收敛为单一事实源：点击发送后，desktop 先插入一条带稳定 token 的本地 `pending` user 气泡，并在同一条 asyncio 路径里把这条消息以 `_pre_saved_token` 预存到 session history，再把同一个 token 透传给 core。后续 `done/error` 收尾只会回写这同一条 user 消息，不会再额外追加第二条 user turn，也不会因为 startup greeting 或 history reload 把 pending 气泡重排成另一条消息。

聊天时间线现在也保持单一路径：消息时间仍以 `ChatMessageModel` 的 `createdAt` 为事实源，日期分隔不在 QML 侧临时回看前后消息，而是在模型侧统一产出 `dividerText` 后交给气泡 delegate 渲染。当前规则只在两种情况下显示轻量分隔线：跨天消息、以及同一天内长间隔消息；普通连续对话不额外堆时间噪音。

普通 user/assistant 气泡的文本布局也已收敛为单一路径：文本占满气泡内容区后使用统一内边距和垂直居中，不再依赖顶锚点硬撑位置；多行与单行消息的上下留白更稳定，避免出现视觉上“文字偏上”的感觉。

普通 user/assistant 气泡的入场动效现在也统一走单一路径：消息插入时直接使用既有 `entrance_style` 元数据驱动方向性滑入、轻微缩放与一次性柔光回落；user 从右侧送入、assistant 从左侧接入，不再依赖额外列表状态或补丁式计时控制。

入口动画契约也已收口为一次性路径：后端只负责在消息首次插入时提供 `entrancePending=true`，`MessageBubble` 播放后立即消费；QML 动画触发与模型 schema 都只认 `entrancePending` 这一条事实源，`entranceConsumed` 已完全删除，不再保留“把同一条消息重新打回待播放”的后门，避免模型层和 QML 层各自维护一套可重播状态。

消息点击反馈现在也统一走单一路径：普通气泡、system 与启动问候都使用气泡内部的 `overlay + ripple + progress` 驱动高光层；高光不再是额外的移动亮片，而是铺在气泡内部的同形渐变层。

ready 阶段的 AI 启动问候统一走 `assistant + entrance_style=greeting` 单一路径：desktop 与外部渠道都复用同一套持久化/未读语义，渲染层仅根据 `entrance_style` 投影 greeting 外观；其中 external greeting 会先按 `channel.send()` 成功与否判定是否落库，落库目标优先跟随 external family 当前 active sibling（如 `imessage:+86...::s7`），找不到 family active 时才回退 natural key；desktop 当前 focus 不再反向影响 external routing。onboarding 继续走普通 assistant 消息链路。历史回放会保留 `format` 与 `entrance_style`，因此 startup greeting 和普通 onboarding 消息在 reload 后都会保持各自语义。

桌面端现在会把子代理线程作为独立只读会话投影出来：子会话进入同一套 `SessionManager -> SessionService -> ChatService/QML` 数据流，并按父会话所在渠道归组、紧跟在父会话下方显示；子会话本身不提供输入框，也不提供删除入口，继续追加提示统一回到主会话，由主代理通过同一 child session key 续接，避免 UI 层再造第二套临时线程状态。

浅色主题的欢迎胶囊与空态 icon 现在也收敛成单一路径：主题判断只以 `desktopPreferences.isDark -> Main.qml` 为事实源，`Main.qml` 负责产出 greeting token、浅色空态底色与简单的 light-asset 路由，`ChatView` / `Sidebar` 只消费最终 `source` 与 token，不再各自维护第二套主题状态。浅色 greeting 会使用更平的实色胶囊和更紧凑的纵向留白，避免渐变在浅底上显脏；空态与侧栏装饰 icon 则统一切到浅色资源，保证浅色模式下仍有足够对比度与识别效率。

Provider 返回错误（如 403）会在聊天中保留为 assistant `status=error` 气泡（红色），并随会话历史持久化，不会再因 history sync 刷新后消失。错误气泡内容会强制按 plain 渲染，避免 markdown/html 片段在实时阶段被解释后出现显示不全，并减少二次布局抖动。

渠道不可用、启动失败、发送失败、停止失败也会复用同一条 desktop system message 链路进入聊天区气泡，不再只停留在终端日志。

会话切换采用 latest-only 单路径：每次切换只保留最新一次历史加载请求（旧请求取消并丢弃结果），历史加载固定走单次 `tail(200)` 准备后提交，不再做会话预热（prefetch）。关键路径与后台路径已分池（会话历史读写走 user IO，渠道轮询走 bg IO），以降低切换抖动。

聊天自动贴底现在收口为 `bottomPinned + reconcile` 单路径：`ChatView` 用 `bottomPinned` 记录当前视口是否仍应锚定底部。用户自己的滚动（键盘/原生滚动）会更新这个事实；冷开已有历史、切会话和 authoritative history 完成这几类“session viewport ready” 生命周期事件，统一由 `ChatService.sessionViewportReady` 上送到 QML，再由 `ChatView.scheduleSessionViewportReady()` 把 `bottomPinned` 拉回 `true` 并触发一次非动画 reconcile。

贴底动作本身与事件解耦：消息追加、`statusUpdated(done|error)`、`contentUpdated` 流式增量、以及 composer 导致的视口高度变化都只触发 `queuePinnedReconcile()`；真正的目标始终只有一个——当前真实 bottom（`originY + contentHeight - height`）。session-ready 这类“大跳转”会直接 instant 到底，避免暴露中间态；运行期离底部较近的增量变化则由可取消的 `SmoothedAnimation` follower 追踪，减少突兀跳动。startup greeting 仍是特殊的可见业务事件，会在追加时直接走 instant 贴底，保证它立刻落在输入框上方的正确位置。

加载边界同样走单路径：若会话切换或 history replay 进入 `historyLoading=true`，贴底 reconcile 会直接停住，不会越过当前 guard 把旧时间线抢到底部；同会话 `modelReset` 若用户原本不在底部，则继续优先恢复旧视口。active 会话的 history replay、tool/system 插入与 transient assistant 尾泡合并规则仍统一收口在 `ChatMessageModel.load_prepared()`；`gateway.py` 现在除了数据更新信号外，还统一提供 `sessionViewportReady` 这种更上游的视图就绪语义，减少 QML 对生命周期细节的直接判断。

桌面端流式显示路径为单一路径：`gateway.py` 通过 `_progressUpdate` 逐 delta 跨线程推送到 UI，不再使用进度合并定时器（coalescing timer），减少“整块落字”体感。应用级默认字体现在优先加载随 app 分发的 `app/resources/fonts/OPPO Sans.ttf`，开发态与打包态都走同一条资源探测路径；仅在内置字体不可用时才回退系统字体族，避免 Qt 落到隐式 `Sans Serif` 别名造成不可控的外观差异。字体选择也只保留应用级这一处字体决策，QML 直接继承 `QGuiApplication` 的全局字体，不再额外维护第二套 family 注入或本地回退。资源文件名保持稳定为 `OPPO Sans.ttf`，这样后续升级字体版本时不需要跟着改运行时代码路径。若要更换品牌字体，只需要修改 `app/main.py` 里的 `BUNDLED_APP_FONT_FILENAME`，并替换 `app/resources/fonts/` 下对应文件。
工具前短说明与 tool hint 现在也走同一条桌面时间线：会先以 display-only assistant 气泡展示，并在 tool 边界封口；后续 final 另起一条回复，不再把 hint 覆盖掉。提示文案按会话语言输出简短 zh/en 版本，只保留对用户有意义的动作摘要。

未命中缓存且历史仍在加载时，聊天面板会显示显式 loading 提示，避免右侧出现长时间黑屏空窗。聊天历史加载、网关启动空态与设置页更新按钮现在统一复用同一套轻量轨道式 loading 视觉，不再混用默认 `BusyIndicator`；侧边栏网关按钮则保留原有启动中动效，让等待中的观感更克制、更顺滑。

侧边栏快速连点切换时，当前激活会话以“用户最新选择的 session key”为事实源；`desktop:local` 视图 active 与 external family active 已经解耦，异步列表刷新不会回滚到旧会话，桌面浏览某个 external sibling 也不会反向改写 core routing。会话一旦提交到当前视图，就会立即写入 `desktop_last_seen_ai_at`，不再等待 history apply 回包后补标已读，减少“已经看过但切走后红点复活”的中间态。

当前正在查看的 active 会话若因外部新消息触发排序更新，侧边栏不会再为了把该会话提到更前面而把列表打回顶部；侧栏最终行模型（header/session/child + active pinning + 展开态 + 未读/运行聚合）已下沉到 `SessionService.sidebarModel`，QML 不再二次拼装 `groupModel`。分组展开态现在完全由用户操作持有：外部消息或 AI 回复触发刷新时，不会再把手动折叠的分组自动展开；若 active 会话就在该折叠分组里，projection 只保留这条 active row 与 header，其余 session 行不会再以 0 高度幽灵行形式留在 `ListView` 里，从根上减少虚拟化抖动，同时保证当前 focus 不会“折叠后消失”。

侧边栏滚动稳态继续收敛到单一路径：`SessionService` 在 sidebar projection 提交前后发出明确的 pre/post 信号，QML 只负责捕获/恢复视图锚点；`ListView` 在 `contentHeight/height` 变化时立即把 `contentY` 夹回合法区间，避免接近底部时因列表重排出现闪烁或短暂空白。

侧边栏分组列表现在彻底收口到 `SessionService.sidebarModel` → `ListView` 单一路径：展开/收起只由模型可见行与 `ListView` 的 displaced 过渡决定，不再叠加额外 sticky overlay 或第二套 header 几何补偿，避免“先重排一次再收口一次”的中间态。

会话运行态也收敛到单一路径：`SessionManager` 现在把 `session_running` 与 `child_status=running` 视为当前进程的 runtime overlay，只在内存里随事件更新，并在 `list_sessions()` / `_load()` 时与稳定 metadata 合并投影；主代理、桌面网关与子代理分别在自己的编排边界显式推送/清理 runtime running 事件，completed/failed/cancelled 这类稳定结果仍正常持久化。active desktop 会话成功收尾时，desktop gateway 不再把“清 `session_running`”和“写 `desktop_last_seen_ai_at`”拆成两次独立可见提交，而是通过 `SessionManager` 的同一条完成路径先清 runtime overlay，再发一次 metadata refresh，避免父/子列表 running 指示器在完成后短暂漂移。`SessionService` 只负责消费这条单一路径并聚合成列表项/分组头的 running badge，QML 不再自己推断 busy 状态，进程重启后也不会把旧 running 残留重新读出来。

会话列表刷新改为真正的提交事件驱动：`SessionManager` 在 `save/update_metadata_only/delete_session` 后统一发出变更事件，`sessionService` 只订阅这一个事件并复用 `refresh()`；不再借用 `statusUpdated` 做补偿刷新。

侧边栏“新对话”保持双入口、单动作：顶部按钮与“暂无会话”空态卡片都只触发现有的新会话动作；当列表为空时，点击空态卡片即可直接创建新会话。

侧边栏会话区也已收敛成单一路径面板：会话标题、未读汇总 badge、加号按钮与分组列表统一包在同一张会话卡片里，不再拆成“外置标题条 + 内部列表卡”两层结构。标题只保留 icon + 文本本体，AI 未读提示沿用 `has_unread` 这一条事实源；顶部汇总 badge、分类未读数 badge 与会话红点统一复用 `UnreadBadge.qml`，避免在多个 delegate 内复制视觉逻辑。

会话列表右侧现在会按同一条后端数据路径显示紧凑相对时间（如 `<1m`、`5m`、`2h`、`3d`）；`SessionItem.qml` 不自行推算时间，只消费 `SessionService` 提供的 `updatedLabel`。时间标签默认保持弱化显示，hover 删除按钮时自然淡出，避免操作态和信息态相互抢位。

Session 持久化层对 `session_meta` 的读写现在统一走同一锁域：会话级写操作仍按 session key 串行，但 `list_sessions()` 不会再看到 `session_meta` 的 delete→add 中间态，因此外部渠道入站后桌面侧边栏不会再因元数据瞬时不可见而“会话消失，重启后才回来”。

会话删除体验已收敛到单一路径：Sidebar 点击删除只发送意图，成功/失败 toast 统一由 `deleteCompleted` 回包决定；本地乐观删除命中的 `deleted` 提交事件会直接复用当前删除事务，不再触发第二次列表重建。若删除已落盘、只是后续 active marker 同步失败，`SessionService` 也会直接按持久化事实刷新收口，不把已删会话从 snapshot 回滚回来。Sidebar 在列表重建前后也不再死守旧 `contentY`，而是按当前可见行锚点恢复视口，让删除上方会话时可见内容跟着稳定收口。`SessionItem` 点击命中也改成稳定的几何分区：主行始终给右侧 trailing action 预留固定保留区，避免 hover/显隐时再改变 pointer owner。

chat/settings 页面切换统一写 `startView`，再由 `currentPageIndex` 绑定投影到 `StackLayout.currentIndex`；Sidebar 不再直接改 `stack.currentIndex`，避免打断绑定后形成第二条导航控制面。

聊天输入区在多行场景采用单一路径高度计算：容器高度由 `contentHeight + padding + inset` 统一钳制；达到最大高度后保留底部可视安全间隙，并在光标位于末尾时自动滚动到末行，确保最后一行与光标始终可见。

输入框点击焦点仅走 `TextArea` 原生路径（移除了容器级聚焦 MouseArea），首击更稳定；窗口层现在只保留统一的 click-away blur 和 pointer refresh：只有显式声明 `baoClickAwayEditor` 的编辑控件才参与窗口级 blur，点击编辑器外时主窗口才会清掉选区并移走焦点。`SettingsSelect` 这类自带 popup 的下拉字段则回到 Qt 原生 `Popup.closePolicy` 负责外点关闭，因此点击别的按钮时，dropdown 会自己收起，同时目标点击继续生效，不再需要窗口层再补第二条 popup dismiss 路径。`MouseButtonRelease` 边界仍会补一次窗口级 pointer 重算，用来处理切页、弹层或显隐变化发生在静止鼠标下时 hover/cursor owner 不能及时刷新的问题；启动完成和应用重新回到 active 时，也会补首轮 pointer refresh，避免整窗 pointer 进入未初始化状态。

输入框的视觉反馈也收敛为一条动效路径：hover/focus 时仅驱动背景、边框与极轻的缩放过渡，失焦时自然回落；文本垂直位置现在通过 `topPadding=15 / bottomPadding=5` 做非对称微调，保持当前胶囊输入框的视觉中心。

聊天 composer 的编辑层现在直接铺满输入框外壳，内部留白只由 `TextArea` 自己的 padding 决定，不再通过 `ScrollView` 再额外缩一圈；因此点击、聚焦与选中反馈会覆盖整个输入框，而不是只落在中间一小块区域。

桌面端测试现在除最小 QML harness 外，还补了一层真实页面集成回归：直接加载 `Main.qml`（从真实对象树进入 `ChatView` / `SettingsView`），验证声明了 `baoClickAwayEditor` 的输入控件会在外部点击时清焦点和选区，`SettingsSelect` 的 popup 外点关闭不会吞掉目标点击，`+ Add LLM Provider` 首击会真正新增并消费展开 pending，同时继续覆盖鼠标释放后的 pointer refresh 和启动/重新激活时的首次 pointer refresh，避免“简化 harness 通过但真实页面回归”。

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
11. Settings 的 `高级 / Advanced` 现在新增了 `配置文件 / Configuration` 区块：会显示当前 `config.jsonc` 路径，并可直接点击 `打开配置目录 / Open Config Folder`
12. 需要查看切换性能时，可用 `BAO_DESKTOP_PROFILE=1 uv run python app/main.py` 启动，终端会输出 `History load` 相关埋点与 `history_load/history_applied` 导航日志
13. 左侧会话面板的未读 AI 提示会先汇总到标题区 badge；当未读会话集合发生变化时，标题区会轻微脉冲一次，切回对应会话后未读会按既有 `desktop_last_seen_ai_at < desktop_last_ai_at` 规则自动收敛

### Skills Workspace

- Skills 工作区现在统一管理内建技能与工作区技能：内建技能只读浏览，工作区技能可创建、编辑、删除。
- `已安装 / 发现` 共用同一页骨架：左侧筛选或输入动作，中间列表，右侧详情；不再拆成多张解释性卡片。
- 发现页支持关键词搜索与技能引用导入。安装时会在当前工作区根目录执行项目级安装，再把产物同步到 `workspace/skills/`，保证 Bao 运行时仍只以工作区技能目录为唯一事实源。
- 详情区默认只展示当前选中技能的说明、状态与可编辑内容；像引用、缺依赖、路径这类信息已收口到详情摘要，不再散落成多张小卡。

## Diagnostics

- 左下角品牌区已收口为固定几何的 `brand dock`：logo 负责进入 Settings，右侧胶囊负责 Diagnostics；品牌区现在只保留三层视觉语义：logo 本体、active 边缘描边、hover 单气泡，避免外圈 glow、多层底板和点击区漂移
- 左下角 logo 右侧的 `日志 / Diagnostics` 入口用于查看 Bao 的结构化运行诊断、日志文件路径和日志尾部
- 该页面是 **控制面诊断入口**，不会把控制面日志混进聊天时间线
- 页面采用扁平化的 2x2 诊断工作台：`Gateway State`、`Log file`、`Recent diagnostics`、`Log tail`
- Diagnostics modal 只保留右上角关闭按钮，底部不再重复放 `Close`
- `发给 Bao / Ask Bao` 仅在存在结构化诊断事件时显示，且默认只发送结构化诊断摘要（+ 必要 observability 摘要），不自动附带日志尾部
- `复制尾部 / Copy Tail` 仍保持独立动作，适合手动补充更多上下文
- `Log tail` 视图会在仍位于底部时自动跟随最新日志；用户手动滚离底部后会立即让出滚动控制，回到底部后再恢复跟随
- 打开 `config.jsonc` 所在目录的入口放在 Settings 的 `高级 / Advanced` 页面，不和 Diagnostics 的日志目录入口混用

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
- 自动检查时，`desktop-update.json` 返回 `404` 会静默视为“暂无更新”；但用户手动点击“检查”时会明确提示 update feed 尚未发布或不可用，避免误报“当前已是最新版本”

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--start-view chat\|settings` | 指定首屏（默认 `chat`） |
| `--smoke` | Smoke 测试模式：加载 QML 后 500ms 自动退出 |
| `--smoke-theme-toggle` | Smoke + 主题切换验证 |
| `--smoke-screenshot <path>` | Smoke + 截图保存（便于 UI 回归） |
| `--seed-messages` | 预填充示例消息（调试用） |
| `--qml <path>` | 覆盖 QML 入口文件 |

## UI 回归

- QML lint：`uv run python app/scripts/run_qmllint.py app/qml/SidebarBrandDock.qml`
- 桌面 smoke 截图：`QT_QPA_PLATFORM=offscreen uv run python app/main.py --smoke-screenshot /tmp/bao-ui.png`
- 当前左下角品牌区回归重点是三条：logo 不得压到 Diagnostics 胶囊；active 态只能表现为边缘描边，不能退回整块圆底；hover 文案必须保持单一扁平气泡

## 当前限制

- 配置保存后需手动重启 Gateway（非热重载，by design）
- 流式回复进行中可以切换会话；旧会话在后台继续执行，UI 隔离显示新会话内容

## 打包

当前默认打包路径已切到 **PyInstaller onedir**；`Nuitka` 保留为备用方案。两条链路分别输出到 `dist-pyinstaller/` 与 `dist/`，互不覆盖。

当前打包链路有四个和 CI 稳定性直接相关的约束，已内置在默认的 PyInstaller 脚本和共用安装脚本里：

- workspace 模板只按 `bao.templates.workspace` package data 打包，不再把 `bao/templates/workspace` 当普通目录手工映射到 bundle 内，也不再对同一路径重复叠加 `--include-package`
- Desktop 只保留 QML 所需 Qt 插件，并显式排除 `tls` 插件，避免 macOS Intel runner 把 Homebrew OpenSSL 动态库拉进 Nuitka 依赖扫描
- Windows 安装器使用仓库自带的 `app/resources/installer/ChineseSimplified.isl`，不再依赖 runner 上的 Inno Setup 安装是否附带该语言文件
- `app/resources` 整体作为资源目录打入产物，因此 `app/resources/fonts/OPPO Sans.ttf` 会随开发态与打包态共用同一条资源路径
- Windows 应用图标也统一收口到 `app/resources/logo.ico`：运行时标题栏、Nuitka EXE 资源与安装器都共用这一个 `.ico`，`logo-circle.png` 只用于应用内 UI
- 安装品牌资源统一收口到 `app/scripts/generate_installer_assets.py`：同一套暖色 token 会同时生成 Windows 安装器 welcome/back/small 图片和 macOS `app/resources/dmg-background.png`，`create_dmg.sh` 与 `package_win_installer.bat` 都会在打包前自动刷新，避免 Win/mac 安装体验与桌面端首屏漂移
- macOS 两条构建链路都会回写同一个 `CFBundleIdentifier`（`io.github.suge8.bao`）和 `NSAppleEventsUsageDescription`，让 Bao.app 能稳定申请 Messages 自动化权限
- 两条 macOS 构建链路都会在回写 `Info.plist` 后立刻重新 `codesign`，避免改完 plist 却留下失效签名，导致 TCC 无法计算 Apple Events 的 designated requirement
- 正式 tag 发布的 `Desktop Release` workflow 在检测到完整 GitHub Secrets 时，会额外导入 Developer ID 证书、对 `.app` 做 hardened runtime 签名、提交 notarization，并在 `.app` / `.dmg` 上执行 staple；若未配置 secrets，CI 仍会继续产出未签名的 macOS 安装包与更新包

如果要在打包后的 macOS App 里启用 iMessage，需要额外完成两条系统授权：

- `Privacy & Security > Automation`：允许 `Bao` 控制 `Messages`
- `Privacy & Security > Full Disk Access`：允许 `Bao.app` 读取 `~/Library/Messages/chat.db` 与附件目录

即使 `CFBundleIdentifier` 与 `NSAppleEventsUsageDescription` 已固定，本地重建、ad-hoc 重新签名或替换旧 `.app` 后，macOS 仍可能把它视为新的 TCC 主体并再次要求授权；这不代表这次权限修复失效。

本地打包前先同步对应构建依赖：默认 PyInstaller 用 `uv sync --extra desktop-build-pyinstaller`，备用 Nuitka 用 `uv sync --extra desktop-build`

```bash
# macOS 默认构建（PyInstaller）
bash app/scripts/build_mac_pyinstaller.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64 --app-path "dist-pyinstaller/dist/Bao.app"
bash app/scripts/create_update_zip.sh --arch arm64 --app-path "dist-pyinstaller/dist/Bao.app"
QT_QPA_PLATFORM=offscreen "dist-pyinstaller/dist/Bao.app/Contents/MacOS/Bao" --smoke

# macOS 备用构建（Nuitka）
bash app/scripts/build_mac.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64 --app-path "dist/Bao.app"
bash app/scripts/create_update_zip.sh --arch arm64 --app-path "dist/Bao.app"

# Windows 默认构建（PyInstaller）
app\scripts\build_win_pyinstaller.bat
app\scripts\package_win_installer.bat --build-root dist-pyinstaller\dist\Bao

# Windows 备用构建（Nuitka）
app\scripts\build_win.bat
app\scripts\package_win_installer.bat --build-root dist\build-win-x64\main.dist
```

推送 `v*` tag 自动触发 GitHub Actions 构建双平台安装包（`desktop-release.yml`），并在构建成功后直接创建正式 Release；随后 `desktop-update-feed.yml` 会下载更新资产、生成 `desktop-update.json`，并发布到 GitHub Pages。release workflow 现已优先复用当前 GitHub-hosted Windows runner 上可用的 Inno Setup，并对已压缩安装包关闭 artifact 二次压缩；PR/非 tag push 使用轻量流水线 `desktop-ci-lite.yml` 做依赖可安装性与脚本校验。

最新桌面发布版本与变更记录详见 [`../CHANGELOG.md`](../CHANGELOG.md)。

完整打包指南见 [`docs/desktop-packaging.md`](../docs/desktop-packaging.md)。

补充：Desktop 后端已增加 `AsyncioRunner` 关闭收敛（先排空再取消残留任务）与 `SessionService.shutdown()` 生命周期清理，用于降低 Qt 测试批量运行时的间歇性崩溃风险。

补充：Settings 下拉字段统一走 `SettingsSelect.qml` 的自定义样式（输入框、箭头动效、弹层选项列表），避免平台默认下拉外观不一致；Provider、渠道与高级折叠内容统一复用 `ExpandReveal.qml`，帮助说明统一复用 `AppModal.qml`。

> 开发细节（架构、测试命令、UI 坑点、技术要点）见 `AGENTS.md`。
