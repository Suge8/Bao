# Changelog

All notable changes to Bao are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/), and this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.26] - 2026-03-13

### Changed

- **Bao 的对外叙事与图示全面收口到 desktop-first 主路径** — README 与官网图示资源现在统一强调桌面端是主入口，同时保留 core、memory、long-run engine、subagents 与 MCP 的真实能力边界。
- **Desktop 左下角品牌区、setup 卡片与安装品牌资源统一到一套暖色视觉系统** — Sidebar brand dock、onboarding/setup 卡片、Windows 安装器 welcome/back/small 图以及 macOS DMG 背景现在共用同一套品牌 token 与图像生成脚本。
- **CLI 启动首屏改为响应式 startup shell，并支持显式 runtime 路径覆盖** — `bao --config` / `--workspace` 现可覆盖运行时路径，启动首屏则按终端宽度自适应展示版本、端口、通道、定时任务、心跳与能力条。
- **Memory recall 与工具大输出治理改为统一单路径** — 长期记忆现在以 fact rows 持久化、按 turn 一次性 recall 注入；`exec`、`read_file`、coding details 与 MCP 文本结果则统一进入 file-backed result 与 artifact/offload 预算链路。
- **渠道群聊策略与回复路由进一步收口** — Telegram、Discord、Feishu、DingTalk 现在都支持更明确的 group policy / reply / attachment / rich card 路径，减少群聊与媒体消息在不同平台上的行为漂移。

### Fixed

- **CLI banner 真图 logo 现在只在支持协议的终端叠加一次，并稳定回退到 ASCII** — startup shell 会优先检测 Ghostty/Kitty/WezTerm/Konsole 的 kitty graphics protocol 与 iTerm2 inline image；支持时叠加透明 PNG logo，不支持时回退到更亮的 Braille ASCII logo，同时内部 overlay 布局探针改为内存输出，不再把白色探针 banner 泄露到终端。
- **定时任务直连主代理时会显式带上 cron tool context** — gateway 的 cron callback 现在在 direct processing 前后成对设置与重置 cron 上下文，避免 reminder 运行路径与普通用户回合混淆。

## [0.3.24] - 2026-03-11

### Changed

- **Desktop direct sends now share one pending-turn pipeline** — desktop chat now keeps a single pending user bubble, pre-saves the same turn into session history before dispatch, preserves bottom-pinned viewport reconciliation, and carries direct-send media attachments through to the core loop.
- **Desktop session and diagnostics surfaces now follow one projection path** — collapsed sidebar groups keep only the active row visible, running/seen updates collapse into one metadata refresh path, the gateway capsule now hands off state transitions smoothly, and diagnostics log tails follow the bottom only while the user stays pinned there.
- **Desktop click-away handling now defers to one native close path** — the window-level dismiss filter now only owns editor blur plus pointer refresh, while `SettingsSelect` popups return to Qt `Popup.closePolicy` so first clicks keep working.
- **Channel lifecycle/reconnect control now follows one shared shell** — `BaseChannel` now owns the stop-event wait and outer reconnect lifecycle, so Discord/WhatsApp/QQ/DingTalk/Feishu/Mochat stop relying on per-channel keepalive/reconnect shells for the same control surface.
- **Provider transient retries now reuse one shared async retry path** — `retry.py` now exposes `run_with_retries()`, and OpenAI chat completions plus Anthropic streaming both route retry timing, retryability checks, and retry hooks through the same helper instead of duplicating per-provider attempt loops.
- **OpenCode short agent names now resolve against unique display names** — Bao can now translate unique oh-my-opencode short names like `Hephaestus` to the current OpenCode display name before launch, while still leaving ambiguous aliases untouched.

## [0.3.23] - 2026-03-10

### Changed

- **Subagent progress tracking now starts from `spawn` JSON** — `spawn` returns a stable schema_version=1 payload, `task.task_id` becomes the public progress query key, and workspace instructions / README stay aligned with the same contract.
- **OpenAI Responses/Codex tool-call replay now uses one shared normalization path** — long `call_id` values, streamed tool arguments, and replayed tool history now flow through the same compat helpers so OpenAI-compatible providers stop diverging on the same protocol surface.
- **Desktop Release can optionally sign and notarize macOS artifacts in CI** — when the required GitHub Secrets are present, the macOS workflow now imports a Developer ID certificate, signs `Bao.app`, notarizes/staples both `.app` and `.dmg`, and otherwise cleanly falls back to unsigned artifacts.
- **Local verification now follows marker-based entrypoints** — pytest markers are declared centrally in `pyproject.toml`, and the repo now ships `scripts/test_targeted.sh`, `scripts/test_smoke.sh`, and `scripts/test_high_risk.sh` so local runs can match the documented fast-path workflow.

### Fixed

- **Gateway/CLI startup greetings now persist only after a real outbound send and land in the active family session** — the runtime channel path now waits for channel readiness, sends through the channel manager, and only then persists the greeting to the currently active sibling for that channel family.
- **Desktop 侧边栏 sticky 分组头不再越界覆盖标题区** — 吸顶分组头现在被限制在会话列表自身的顶部裁剪视口内，被下一个分组顶走时只会在列表内退出，不再漏到上方标题区域。
- **Desktop/外部渠道的运行态不再作为跨重启脏 metadata 残留** — `SessionManager` 现将 `session_running` 与 `child_status=running` 收口为当前进程的 runtime overlay，并在列会话/加载会话时与稳定 metadata 合并；主代理、desktop gateway 与 subagent 在各自编排边界显式推送/清理运行态，侧栏绿点继续事件驱动更新，但应用重启后不会再从磁盘读回旧 running 状态。
- **Desktop 设置页首击不再被窗口级失焦吞掉** — `WindowFocusDismissFilter` 现在只对显式声明 `baoClickAwayEditor` 的编辑器执行 click-away blur，并把失焦收口在点击完成之后；Settings 的 tab、Provider 展开头与“+ 添加 LLM 提供商”不再出现先失焦、第二次点击才生效的竞态。
- **Desktop 设置页首击路径进一步收口** — `WindowFocusDismissFilter` 现在只负责 editor click-away blur 与 pointer refresh；`SettingsSelect` 的 dropdown 外点关闭回归 Qt 原生 `Popup.closePolicy`，打开下拉后再点 `Save`、渠道头或 `+ 添加 LLM Provider` 不会再先关闭弹层、第二次才生效，而 `+ Add LLM Provider` 也会在首击后立即展开并滚动到新增卡片。
- **iMessage send failures now surface as actionable runtime errors** — AppleScript send failures, including `-1743` automation denials, now raise back to the caller so desktop and tests can distinguish “send failed” from “send silently disappeared.”

## [0.3.22] - 2026-03-09

### Changed

- **Desktop 启动问候与 greeting 视觉语义改为统一的 assistant 单一路径** — desktop 与外部渠道的 startup/onboarding 问候现在都会按 assistant 消息持久化，并保留 `entrance_style` 供 UI 投影 greeting 外观，避免会话历史、未读与启动目标在 system/assistant 两套语义之间漂移。
- **Desktop focus 不再反向污染 external startup routing** — Desktop 当前浏览的 external sibling 不再写回 external family active；external startup greeting 会继续跟随 core 维护的 family active，而不是被桌面当前 focus 改写。
- **Desktop 打包指南正式纳入仓库发布文档链路** — `docs/desktop-packaging.md` 现在作为受版本控制的正式文档保留，同时 `.gitignore` 继续默认忽略其他本地 `docs/*`，只显式放行这份发布文档，消除“README 可见但 CI checkout 缺失”的状态分裂。

### Fixed

- **Desktop 启动问候不再误落到当前外部会话或丢失持久化 entrance_style** — `SessionService` 与 `ChatService` 现在会优先解析 desktop 启动目标，会话持久化同步保留 greeting/assistant entrance style，切到外部渠道时也不会把启动问候写错会话或在 reload 后退化成普通 assistant 气泡。
- **Gateway/CLI 的 startup greeting 会同步落库到当前 family active 会话** — 外部 ready/onboarding 问候在真实发送成功后会优先写入该渠道 family 当前 active sibling（如 `imessage:+86...::s7`），找不到 active sibling 时再回退 natural key；桌面端 reload、未读与历史回放能看到与 `/new` / 当前会话续接一致的启动消息，不再回落到旧 sibling。

## [0.3.21] - 2026-03-09

### Fixed

- **iMessage 发送失败现在会给出明确的自动化授权提示** — 当 AppleScript 因 `-1743` 被 TCC 拒绝时，日志会直接提示为 Bao 授予 `Automation -> Messages` 权限，减少桌面打包后排查 iMessage 不可用的成本。
- **桌面更新检查区分自动静默与手动反馈** — 自动检查时仍把 `desktop-update.json` 的 `404` 视为“尚未发布”，但用户手动点击检查时会明确提示 update feed 未发布，避免把配置缺口误报成“已是最新版本”。
- **macOS Desktop 打包链路补齐稳定的包标识与 Automation 权限声明** — Nuitka/PyInstaller 两条构建脚本都会写回统一的 `CFBundleIdentifier` 与 `NSAppleEventsUsageDescription`，让 Bao.app 更稳定地申请 Messages 自动化权限。
- **Desktop Release workflow 现会直接创建正式 GitHub Release** — tag 构建成功后不再默认留在 draft 状态，后续 update feed 可以沿同一发布链路继续消费正式 release 资产。

## [0.3.20] - 2026-03-09

### Added

- **Desktop 侧边栏现可把子代理线程投影为只读子会话** — 子线程会按父会话所在渠道归组、紧跟父会话显示，并在 sticky group header 与会话项上统一展示运行态，避免 UI 层再维护第二套临时线程状态。
- **主/子代理的 tool hint 与 child session 结果现在会落成可见的协作上下文** — tool hint 会以 display-only assistant turn 的形式留在时间线里，子会话也会持久化 label/status/result summary，桌面端可以稳定展示过程提示而不吞掉最终回复。

### Changed

- **Skills 索引升级为精确路径元数据入口** — skill summary 现在携带 `path/source/available`，并缓存 bootstrap/skill 文件读取结果；命中后代理可直接按索引路径读取最匹配的 `SKILL.md`。
- **Bao 数据目录收口为共享 helper** — 配置文件、媒体下载目录与 OpenAI-compatible API mode cache 统一走 `~/.bao` 数据根路径；Desktop 设置页也新增配置文件路径展示与“打开配置目录”入口。

### Fixed

- **Desktop 会话投影与 metadata 改写稳态进一步收口** — `SessionManager` 不再让 `session_meta` 暴露 delete→add 中间态，外部渠道入站时桌面侧边栏不会再因为 metadata 瞬时不可见而让会话短暂消失。
- **渠道 progress/tool hint 边界不再残留旧缓冲状态** — tool hint 发送前后会清空 progress buffer，Telegram/Discord/飞书/WhatsApp 的媒体落盘路径也统一走共享媒体目录，减少跨渠道提示与附件路径漂移。
- **Desktop 启动与配置失败现在有统一运行诊断落点** — 配置加载失败、日志目录 fallback 与桌面启动早期错误都会写入 runtime diagnostics，便于在 Settings/Diagnostics 中直接定位问题。

## [0.3.19] - 2026-03-08

### Fixed

- **Windows 安装器打包入口现在会把 build root 统一归一化为绝对路径** — `app/scripts/package_win_installer.bat` 会先把 `PROJECT_ROOT` 与最终 `BUILD_ROOT` 解析成完整路径后再传给 Inno Setup，因此无论 workflow 或本地命令传的是 `dist-pyinstaller\dist\Bao` 这种相对路径，`bao_installer.iss` 都不会再把它误解为相对 `app/scripts/` 的目录，避免 Release/CI 在 `Create installer` 阶段报 `No files found matching ...`。

## [0.3.18] - 2026-03-08

### Fixed

- **Desktop Release 早期 guard-rail 测试不再依赖本地工程笔记文件** — `tests/test_desktop_build_scripts.py` 现仅断言随仓库跟踪的脚本与 `app/README.md` 契约，不再读取未进入 Git 的 `AGENTS.md` 与 `docs/*.md`，避免本地通过但 CI checkout 后因 `FileNotFoundError` 提前失败。

## [0.3.17] - 2026-03-08

### Added

- **Runtime diagnostics 已形成单一路径闭环** — 新增 `runtime_diagnostics` 事实源与同名只读工具，Agent/子代理可记录结构化内部错误、tool observability 与日志尾部；Desktop 侧新增 Diagnostics 工作台，可查看 recent diagnostics、log tail、log file，并按需把结构化摘要发给 Bao。
- **Agent Browser 工具接入主/子代理** — 新增 `agent_browser` 内置工具与配套 skill，主代理、子代理和 `web_fetch` 现在都能在遇到交互式页面、表单或 challenge 页面时复用同一条浏览器执行路径。

### Changed

- **Desktop 界面语言与主题偏好改为本地持久化** — `ui.language` 不再作为共享 runtime config 字段；Desktop 改由 `QSettings` 驱动 `desktopPreferences` 单一事实源，同步管理界面语言、浅深色主题与系统主题跟随语义。
- **Desktop 打包主链切换为 PyInstaller onedir** — 新增 `desktop-build-pyinstaller` extra、macOS/Windows PyInstaller 构建脚本与对应 CI/workflow；Nuitka 保留为备用链路，installer 资源、图标与字体也统一收口到新的打包事实源。

### Fixed

- **子代理完成回传收口为内部结构化事件** — `subagent.py` 与 `loop.py` 现在通过共享的 `subagent_result` schema 交接完成态：子代理只发布 `metadata.system_event`，父代理消费后仅保留面向用户的 assistant 摘要；Desktop 不再回显 raw 子代理 system 气泡。
- **Desktop 会话冷开、未读与历史贴合路径进一步稳定** — `SessionManager` 新增 `session_display_tail` companion 表与内存 tail cache，`ChatService`/`SessionService` 改为围绕 active session summary、known-empty session 与 latest-only history apply 收口，减少切会话黑屏、红点复活和历史回放抖动。
- **Desktop 浅色主题 icon 与欢迎胶囊继续收口** — `Main.qml` 现在统一产出浅色空态/侧栏装饰 icon 的主题 source 与相关 token，`ChatView.qml`、`Sidebar.qml` 只消费解析后的结果；浅色 greeting 胶囊和 light icon 资源也改为更高对比的单一路径。

## [0.3.16] - 2026-03-07

### Fixed

- **Desktop packaging guard-rail 测试重新对齐 Windows 与安装器资源路径** — `tests/test_desktop_build_scripts.py` 改为用 raw string 断言 Windows build script 路径，避免 `\a` 之类的反斜杠转义在 pytest 里先把检查自身炸掉；同时补回对仓库内 `ChineseSimplified.isl` 和 `.iss` 引用路径的显式断言，让 release workflow 在昂贵打包开始前就能更稳定地发现脚本回归。

## [0.3.15] - 2026-03-07

### Fixed

- **Windows 安装器不再依赖 runner 自带简体中文语言包** — `app/scripts/bao_installer.iss` 改为直接引用仓库内的 `app/resources/installer/ChineseSimplified.isl`，`resolve_inno_setup.py` 也同步只要求宿主机具备 `Default.isl`，避免 GitHub-hosted Windows runner 因 Inno Setup 安装内容差异在编译阶段报缺少 `ChineseSimplified.isl`。
- **Desktop Nuitka 打包收口到单一路径模板资源声明** — macOS/Windows 构建脚本删除了对 `bao.templates.workspace*` 的重复 `--include-package` 声明，仅保留 `--include-package-data`，避免再次把编译产物与复制的数据文件同时写进 `bao/templates` 命名空间，重现 `.app` 构建阶段的 `NotADirectoryError`。

## [0.3.14] - 2026-03-07

### Fixed

- **Desktop Release 仍会误拒绝 Chocolatey 的 `iscc.exe` shim** — `resolve_inno_setup.py` 现在把 Chocolatey `bin` 下可执行的 shim 视为有效编译器入口，不再要求 shim 同目录存在 `Default.isl` 或语言文件；这与 `package_win_installer.bat` 直接执行返回路径的真实用法保持一致。

## [0.3.13] - 2026-03-07

### Fixed

- **Desktop Release Windows 预检误把 Chocolatey shim 当成 Inno Setup 安装根** — `resolve_inno_setup.py` 现在会把 `Chocolatey\bin\iscc.exe` 展开为真实包内 `ISCC.exe` 候选路径后再校验 `Default.isl` 与语言文件，避免 runner 明明已装 Inno Setup 仍在 preflight 阶段报缺文件。
- **release 校验任务被 uv cache 服务抖动误伤** — `desktop-release.yml` 的 `validate-version` job 不再依赖 `setup-uv` 缓存，避免 GitHub cache `400` 让轻量版本校验无谓失败。

## [0.3.12] - 2026-03-07

### Changed

- **SessionManager 冷启动路径进一步收口** — LanceDB 连接与 `session_meta/session_messages` 表改为真正按职责懒打开，仅在首次访问对应表时初始化；建索引也只在新表创建时执行，避免 Desktop/UI 线程把会话存储提前拉热。
- **Desktop 构建依赖改为单一事实源** — `nuitka`、`ordered-set`、`zstandard` 被收口到新的 `desktop-build` extra，macOS/Windows 本地脚本与轻量 CI 统一改用 `uv sync --extra desktop-build --frozen`，不再混用 `uv sync` 与额外 `uv pip install`。

### Fixed

- **Session 持久化追加路径不再误保留旧消息** — `SessionManager.save()` 现在会先验证已落库消息是否仍与当前消息前缀一致；一旦中间消息被改写，就走整表重写而不是错误追加，避免 reload 后读到旧内容。
- **Windows 安装器打包不再假设 `iscc` 已在 PATH** — `package_win_installer.bat` 会先通过 `resolve_inno_setup.py` 解析可用的 Inno Setup 编译器，并校验必需语言文件存在，缺失时直接给出明确错误。
- **Desktop Release 无需重新打 tag 也能重建产物** — release workflow 新增 `workflow_dispatch.release_ref` 入口，可在修复 workflow 后直接针对既有 tag 重建同版本产物，并在 Windows 正式构建前先做 Inno Setup toolchain 预检。

## [0.3.11] - 2026-03-07

### Fixed

- **Desktop loading 视觉已统一** — 聊天历史加载、网关启动空态与设置页更新按钮现统一复用同一套轨道式 loading 语言，移除默认 `BusyIndicator`；侧边栏网关按钮则保留原有启动中动效，让等待态更丝滑、克制且一致。
- **Desktop 配置保存稳态** — 首次安装生成的默认 `config.jsonc` 在一次保存中补齐多个缺失配置键时，不再因为 JSONC patch 少逗号而报 `Patch failed`；失败仍保持可见报错，不会把配置写成半有效状态。
- **Desktop 消息气泡入场感缺失** — user 消息接入既有 `entrance_style` 单一路径，普通 user/assistant 气泡统一改为带方向感的滑入、轻微缩放与柔光回落，避免看起来像没有动效或动画未生效。
- **Desktop system 消息偶发不贴底** — `ChatView` 的自动贴底改为先收敛 `ListView` 布局、再统一滚到底部，并直接读取当前使用中的消息模型；“Gateway started / 网关已启动” 这类 system 消息追加后会稳定贴底。
- **Desktop entrance 语义与贴底 guard 收口** — history refresh 现在会正确识别 system `system/greeting` 的持久视觉差异；同时 deferred follow 也会尊重 `historyLoading`，避免切会话或回放开始后被旧的贴底回调强行拉到底部。
- **Desktop 入口动画重播入口已删除** — 消息入口动画现在固定为首次插入时的一次性播放，移除了后端把同一条消息重新标记为 pending 的假重播路径，减少模型/QML 双侧状态分裂。
- **Desktop 历史显示语义已对齐实时路径** — session display history 现在会保留 `format` 和 `entrance_style`，assistant 历史消息 reload 后不再退化为 plain；history fingerprint 也改为基于准备后的显示消息，前序消息的视觉语义变化不会再被“最后一条没变”的短路挡住。
- **Desktop 入口动画状态与字体回退进一步收口** — `entranceConsumed` 已从模型/QML/测试中彻底删除，入口动画只保留 `entrancePending` 单一事实源；桌面端启动时也会显式绑定可用系统字体，避免 Qt 落回 `Sans Serif` 别名提示。
- **Desktop macOS Nuitka 打包收口** — workspace 模板改为按 `bao.templates.workspace` package data 打包，避免 `.app` 内 `bao/templates` 命名空间冲突触发 `NotADirectoryError`；同时显式排除 Qt `tls` 插件，避免 Intel macOS runner 因 Homebrew `libcrypto.dylib` 依赖扫描崩溃。

## [0.3.10] - 2026-03-06

### Added

- **打包模板资源正式入库** — `bao/templates/workspace/{en,zh}` 的 onboarding 模板现已随仓库跟踪，GitHub Actions checkout 后可直接参与桌面构建与首次引导。

### Fixed

- **Desktop Release 三平台前置失败** — macOS/Windows Nuitka 脚本恢复为打包稳定存在的 `bao/templates/workspace` 根目录，不再对子语言目录逐条声明，避免在参数解析阶段因源目录不可见而提前退出。
- **包内模板被误忽略** — `.gitignore` 的 `workspace/` 规则改为仅匹配仓库根 `/workspace/`，不再误伤 `bao/templates/workspace/` 下的包内模板资源。
- **桌面打包回归缺少护栏** — 新增 build-script 回归测试，锁定模板目录存在性与 `workspace` 根目录打包契约，避免后续再次把发布流程改回脆弱路径。

## [0.3.9] - 2026-03-06

### Added

- **Desktop setup 首屏引导** — 未完成配置时主窗口直接进入 Settings，并在页面顶部展示 3 步引导，帮助首次启动更快完成 Provider 与模型配置。

### Changed

- **Desktop setup 单一路径收敛** — `Main.qml` 以 `setupMode`/`currentPageIndex` 作为唯一入口事实源；未完成配置时隐藏侧边栏与网关入口，避免进入半配置中间态。
- **Settings provider 保存语义收敛** — 新增 provider、provider 改名、带 `.` 的 provider 名称以及 `ui.update.*` 配置合并，统一走整块对象写回路径，减少 dot-path 歧义和旧键残留。
- **Desktop 打包模板资源对齐** — macOS/Windows Nuitka 脚本改为显式打包 `bao/templates/workspace/{en,zh}` 子目录，并在 Windows 构建中关闭控制台窗口，保证安装包资源与运行形态一致。

### Fixed

- **Desktop 配置保存原子化** — `ConfigService.save()` 改为临时文件写入后原子替换，避免写盘中断时留下半写配置。
- **Desktop GUI 测试组合崩溃** — `test_config_service.py` 统一使用 `QGuiApplication` 基座，修复与 QML 集成测试同进程运行时的 Qt abort。

## [0.3.8] - 2026-03-06

### Changed

- **Desktop 气泡点击反馈升级** — `MessageBubble` 的普通消息、system 与启动问候点击反馈统一为气泡内部的 `overlay + ripple + progress` 高光层，避免高光作为独立亮片压在气泡外侧，交互更完整也更稳定。
- **Desktop 输入区视觉收口** — 发送按钮改为基于 `sizeButton` 的真圆形按钮，图标更新为更现代的上箭头 glyph，并在按钮组件内部统一提供 hover/press 缩放、柔光与高光反馈。
- **Desktop 输入框聚焦动效升级** — 聊天 composer 的 hover/focus 统一驱动背景、边框、aura 与高光过渡，聚焦和失焦都更连贯，不再只是边框硬切。

### Fixed

- **Desktop 普通气泡文字偏上** — `MessageBubble` 的普通 user/assistant 气泡改为统一内容区内边距 + 垂直居中布局，不再依赖顶锚点硬撑文本位置，单行和多行消息的上下留白更稳定。
- **Desktop 输入框点击外部后仍保持选中态** — 聊天页补上统一 click-away 失焦出口，点击 composer 外部会转移焦点并清除输入选区，避免焦点视觉态残留。
- **Desktop pointer 全局偶发失效** — `WindowFocusDismissFilter` 在 `MouseButtonRelease` 边界统一补一次窗口级 pointer 重算；点击导致的切页、弹层或显隐变化即使发生在静止鼠标下，也会立即刷新 hover/cursor owner，不再需要切到别的应用再切回来恢复。
- **Desktop 会话项删除与选中抢事件** — `SessionItem` 的主点击区在删除按钮可见时会同步收缩右边界，主行选中与右侧删除不再共享同一命中区。

## [0.3.7] - 2026-03-06

### Changed

- **Desktop 打包并行编译** — macOS/Windows 的 Nuitka 构建启用 `--jobs` 并行编译（默认按 CPU 核心数；可通过 `NUITKA_JOBS` 覆盖），减少 CI 构建耗时。

### Fixed

- **macOS CI ccache 编译器探测失败** — 通过 `ccache` 编译器 wrapper 启用编译缓存，避免 `CC="ccache clang"` 触发 Nuitka/Scons 无法识别 clang 版本的致命错误。
- **Windows 打包脚本解释器不一致** — 构建与打包脚本统一使用 `uv run python`，避免 CI 中系统 `python` 找不到 Nuitka/PySide6。
- **workspace 模板资源打包缺失/告警** — 仅打包 `bao/templates/workspace` 到分发包内路径，避免 `bao/templates` 空目录告警并确保 onboarding 模板可用。
- **Windows 文件描述编码异常** — `--windows-file-description` 改为 ASCII（`Bao - ...`），避免控制台/元数据出现乱码。

## [0.3.6] - 2026-03-06

### Added

- **通道就绪等待** — ChannelManager 支持 `wait_started/wait_ready`，启动问候会等待对应 channel ready 再发送，减少启动竞态。

### Changed

- **启动问候提示词分层** — startup greeting 的 system 注入顺序调整为 `INSTRUCTIONS.md → PERSONA.md → Runtime`，user 侧仅发送最小内部事件 `{"event":"system.user_online"}`；若配置 `agents.defaults.utilityModel` 则启动问候优先使用 utility provider+model。
- **工具暴露策略** — `read_file/write_file/edit_file/list_dir` 从 code bundle 调整到 core bundle，保证偏好/人设类对话也能看到文件工具（`toolExposure.mode=auto`）。
- **Responses API 流式输出** — Responses 路径改为 SSE 增量流式解析，且在 system prompt 疑似被忽略时自动回退 Chat Completions。
- **Desktop 会话切换单路径** — 移除会话预加载与进度合并定时器，历史加载按 latest-only 单路径收敛，流式内容逐 delta 推送。

### Fixed

- **Responses API system 丢失** — prompt caching 产生的 system content blocks 现在可被 Responses 兼容层正确提取为 `instructions`，避免被上游默认 Codex system prompt 覆盖。
- **Responses SSE 收口** — 兼容流式事件在末尾不带 trailing blank separator 的收口情况。
- **Anthropic base_url 双 v1** — 代理 base_url 末尾带 `/v1` 时不再拼出 `/v1/v1/messages`。
- **推理强度 off 默认 thinking** — `reasoningEffort=off` 会显式禁用 Claude 的默认 extended thinking（不再自动启用 `adaptive + 1024`）。
- **Session 保存与并发** — SessionManager 按 session key 收敛锁域并优化 save 追加路径，降低高频切换/持久化开销。

## [0.3.5] - 2026-03-05

### Added

- **Desktop 推理强度设置项** — Settings 的 Agent Defaults 新增 `reasoningEffort` 选项（`Auto/off/low/medium/high`），可直接通过界面保存到配置

### Changed

- **记忆检索延迟优化** — 低信息输入（如确认/寒暄短句）跳过重检索，重复查询复用检索缓存；记忆/经验发生变更时自动失效缓存并按修订号隔离
- **无 token 记忆注入语义调整** — `get_relevant_memory_context` 在 query 无有效 token 时返回空注入路径，不再回退整段全量长期记忆
- **推理强度 `off` 语义打通** — OpenAI/OpenAI Codex/Anthropic/Gemini 统一支持 `reasoningEffort=off`，`off` 时不再发送对应 reasoning/thinking 配置
- **Desktop 会话列表刷新改为提交事件驱动** — `SessionManager` 在 `save/update_metadata_only/delete_session` 后统一发出变更事件，`SessionService` 直接订阅提交并复用 `refresh()`，不再借用 `ChatService.statusUpdated` 做补偿刷新
- **Desktop 历史加载线程化** — 会话历史读取与 `prepare_history` 改为 `asyncio.to_thread(...)` 执行，降低共享 asyncio loop 被同步 I/O 阻塞的概率
- **Desktop 预加载触发策略收敛** — 取消 `setSessionManager()` 自动 initial prefetch；切换会话后仅在当前会话 full load 完成时触发 anchor prefetch，优先保障首屏加载

### Fixed

- **Desktop finalize 气泡瞬闪** — `ChatMessageModel.load_prepared()` 的渲染等价判定改为仅比较 `role/content/format/status`（忽略 `entrance*` 差异），避免回复收口后因 history refresh 触发不必要 reset；同时将 `ChatView/MessageBubble` 的 `role` fallback 统一为 `assistant`，消除 delegate 重建空窗误闪 user 大气泡
- **Desktop 会话标题可读性** — 无 `metadata.title` 时，`desktop:local` 显示为 `default`，`desktop:local::name` 显示为 `name`，避免 UI 直接暴露内部会话 key
- **标题生成长期空缺** — 移除标题生成固定轮次窗口；会话无标题时持续尝试异步生成，并维持 `_title_generation_inflight` 单点防重
- **Desktop 新消息红点残留** — 未读判定收敛为 AI 时间戳单一路径（`desktop_last_ai_at` vs `desktop_last_seen_ai_at`），移除 `updated_at` 比较、模型层 `clear_unread` 与刷新合并补丁；修复“已查看后重启仍出现红点”问题，并保持跨渠道新 AI 消息提示一致
- **Desktop 启动期 pointer 偶发丢失** — `Sidebar` 会话分组重建改为单触发直连（`onSessionsChanged` 直接重建），移除延迟 `Timer` 与 `sessionList.model = null` detach/reattach 路径，降低启动中间态导致的 hover/cursor 空窗
- **Desktop 删除反馈延迟** — 会话删除成功提示改为点击即显；失败仍由异步回包覆盖提示，避免“删除成功 toast 明显滞后”
- **Desktop 删除后侧栏位移** — 本地乐观删除命中的 `deleted` 提交事件不再触发第二次列表重建；若删除已落盘但 active marker 后续同步失败，也直接按持久化事实刷新收口，不再把已删会话回滚回 UI。Sidebar 同时从机械恢复 `contentY` 改为按当前可见行锚点恢复视口，删除上方会话时可见内容更稳定
- **Desktop 输入框首击偶发无效** — 移除输入容器覆盖层 `MouseArea`，点击焦点收敛到 `TextArea` 原生路径
- **Desktop 输入框垂直偏移** — 调整 `TextArea` 内边距为 `topPadding=6 / bottomPadding=2`，对齐 ring 视觉中心

## [0.3.4] - 2026-03-04

### Changed

- **工具路由一致性增强** — `toolExposure.mode=auto` 下将 `exec` 纳入 core/rescue，并在执行层复用同轮 allowlist，杜绝“未暴露工具仍被执行”
- **非流式通道退出语义调整** — iMessage/WhatsApp 停止时改为清空进度缓冲（clear）而非强制 flush，避免退出时补发陈旧半句

### Fixed

- **forced-final 工具执行缺口** — 强制收口阶段采用空 allowlist，provider 异常回传的 `tool_call` 不会被执行
- **重复抑制日志错位** — 仅在实际会发布 outbound 时记录 `💬 回复消息 / out`，避免“日志显示已回复但用户未收到”的误导
- **进度清理残留状态** — `ProgressBuffer.clear_only` 补齐 `_open/_last_time` 清理，避免多 chat_id 长时运行状态堆积

## [0.3.3] - 2026-03-03

### Added

- **子代理委派可见提示** — `spawn` 成功后立即推送“已委派子代理处理中”状态消息，并按会话语言（zh/en）输出，保留线程元数据用于 Slack thread 对齐

### Changed

- **消息工具线程上下文继承增强** — `message` 默认目标会继承会话级 reply metadata（`thread_ts/channel_type`），并对 channel/chat_id 做规范化比较，减少 thread 脱线
- **空响应兜底本地化扩展** — 用户路径与 system 路径在 `final_content` 为空或仅空白时统一走短文本本地化兜底

### Fixed

- **message 单轮并发竞态** — 引入每轮发送锁，修复并发工具调用下可能双发的问题
- **工具取消语义一致性** — `message` 与 `spawn` 在通知发送阶段遇到 `CancelledError` 时透传取消，不再被包装为普通错误
- **spawn 成功结果解析鲁棒性** — 改为基于标准化文本 + `task_id` 正则提取，前导空白等格式波动不再导致通知丢失

## [0.3.2] - 2026-03-03

### Added

- **工具路由打分与自动扩容** — `toolExposure.mode=auto` 下按意图和参数命中对工具打分，先 top-K 曝光，连续未触发工具调用时自动扩容并可回退全量曝光
- **悬空 tool_call 自愈** — provider 调用前自动补齐缺失的 tool 结果占位，避免 API 因 assistant/tool 不配对而拒绝请求（主代理与子代理一致）

### Changed

- **记忆检索升级为混合候选** — 向量召回与 BM25 文本候选合并后统一 rerank，新增文本信号权重，检索稳定性更高
- **长期记忆写入去重优化** — long-term 内容归一化后若无变化则跳过 delete/re-insert 与 embedding 调度，减少无效写入与额外开销
- **Anthropic 推理预算映射** — `reasoning_effort` 映射到更高 `budget_tokens`（`low=2048` / `medium=4096` / `high=8192`），thinking 默认类型改为 `adaptive`

### Fixed

- **/session 选择漂移** — 会话列表展示时缓存 key 顺序，按序号选择时优先使用缓存快照，避免中间 metadata 更新导致序号错位
- **Runtime 主机信息可见性** — system prompt 的 Runtime 区块增加 `Host:` 前缀并声明为权威事实，降低重复询问已有环境信息

## [0.3.1] - 2026-03-03

### Changed

- **桌面自动化默认启用** — `mss`/`pyautogui`/`pillow-heif` 从可选依赖移入主依赖，`desktop.enabled` 默认 `true`；新用户安装即可用，无需额外步骤
- **配置模板精简** — `toolExposure` 移除 `bundles` 字段（代码默认兜底，不暴露给用户）；桌面自动化注释去掉过时的安装提示

## [0.3.0] - 2026-03-03

### Added

- **计划系统增强** — 计划通知全面本地化，`create_plan` / `update_plan_step` / `clear_plan` 推送按会话语言偏好（中/英）输出；Markdown 渠道发送 Markdown 模板，纯文本渠道自动回退；Slack thread 会话保留线程上下文；渲染安全转义特殊符号
- **流式事件协议** — Agent loop 新增结构化 stream-event 协议，支持外部消费者（UI/自动化）订阅实时进度和工具执行事件
- **工具错误遥测** — 结构化工具错误 telemetry，记录工具选择命中率、参数填充成功率、post-error 调用代理等质量指标
- **一键安装器** — 新增 macOS (`install.sh`) 和 Windows (`install.ps1`) 一键安装脚本，自动检测并补齐 Python/uv 依赖
- **PyPI 发布流程** — 支持 `bao-ai` 包通过 PyPI 分发，`pip install bao-ai` 即可安装

## [0.2.1] - 2026-03-03

### Changed

- **Agent Loop 解耦** — 将 `loop.py` 拆解为多个职责清晰的方法，降低单方法复杂度
- **Subagent Manager 解耦** — 将 `subagent.py` 拆解为聚焦方法，提升可读性和可测试性
- **Coding Agent 解耦** — 将 `coding_agent_base.py` 的 `execute` 方法拆解为多个聚焦方法
- **MCP 连接逻辑提取** — 将 MCP 连接 helper 提取为模块级函数，减少类内耦合
- **启动问候逻辑提取** — 将 `gateway/builder.py` 的启动问候 helper 提取为模块级函数
- **Office 技能共享层** — 提取 `_office_shared` 共享实现，统一 Office validators 的导入契约和 `schemas_dir` 绑定

### Added

- Office validators wrapper 导入契约测试，验证单进程多 skill 连续导入不串线
- Bridge `package-lock.json`，确保 Node 依赖可复现安装

### Docs

- README 补充 planning 工具说明和 office validators 测试用法

## [0.2.0] - 2026-03-03

### Added

- **自动规划系统** — 新增 `create_plan` / `update_plan_step` / `clear_plan` 三个原子工具，AI 遇到多步骤任务自动创建计划并逐步更新
  - Planning 状态模型（`plan.py`）：纯函数式，`Session.metadata` 持久化
  - Agent loop 集成：tool_hints 包含 WHEN/HOW/SKIP 触发策略；活跃计划以 `## Current Plan` 注入上下文，完成后自动归档
  - Context builder 集成：`build_messages()` 接受 `plan_state` 参数，done 时停止注入
  - Planning 测试套件
- **Docker 安全加固** — 非 root 运行、资源限制、health check；新增 WhatsApp bridge 服务（Docker Compose profile）
- **Docker 环境模板** — `.env.docker.example` + `.gitignore` 白名单，Docker 专用配置与本地运行隔离

### Fixed

- CI/CD：修复 macOS runner 配置和 Nuitka 环境变量问题

## [0.1.0] - 2026-03-03

Bao 首个正式版本。

### Core Agent

- **Agent 主循环** — 完整的 agent loop，含 retry with reflection（连续 3 次失败后反思策略）、per-session lock、generation barrier（阻止过期响应发出）
- **协作式软中断** — 同会话新消息通过流式阶段 + 工具启动前 + 工具执行中 + 工具边界四层检查实现软中断；`/stop` 保留为硬中断（natural + active 双 key 取消）
- **长任务引擎** — 轨迹压缩（每 5 步 RE-TRAC 式递归重置）+ T# 编号前缀 + 条件性自审计 + 充分性检查（累计步数 gate，命中后优先禁用 tools 收口）
- **模块提取** — `shared.py`（7 个共享函数）、`commands.py`（/model + /session 命令）、`experience.py`（经验提取逻辑）从 loop.py 独立

### Memory & Experience

- **分类长期记忆** — preference / personal / project / general 四分类独立存储，写入硬帽（`MEMORY_CATEGORY_CAPS`）+ 去重 + 智能截断
- **列式经验引擎** — 闭环学习（Laplace 平滑置信度 + 冲突检测 + 负面学习 + 主动遗忘）、BM25 降级检索、多因子纯 Python rerank、检索命中追踪
- **记忆管理** — `/memory` 交互式斜杠命令（4 状态状态机：list → detail → edit/delete），Gemini embedding 支持
- **条件 LTM 注入** — 按 query 相关性过滤分类，中文 CJK bigram + 混合脚本双提取 tokenizer，记忆/经验预算控制（`MAX_LONG_TERM_MEMORY_CHARS=1500`）

### Context & Prompt

- **分层上下文管理** — Layer 1 大输出外置 + Layer 2 自动压实（保留最近对话轮次 + 最近工具块）
- **用户图片自动压缩** — 大于 1MB 或非原生格式自动 JPEG 压缩（EXIF 修正 + 透明通道合成 + 1568px 长边缩放）
- **渠道格式指引** — 按渠道注入 system prompt，新增渠道需同步添加
- **Runtime Context** — 运行时元数据拼入 system prompt 的 `## Runtime (actual host)` section，`Host:` 前缀标识主机环境，身份描述声明 Runtime 为权威事实
- **Thinking Protocol** — 条件跳过 + channel format hints

### Subagent

- **后台子代理** — 独立运行，主代理随时响应；里程碑推送（每 5 轮自动汇报）
- **进度追踪** — `check_tasks` 双格式输出（brief 单行 + detailed 多行）、`check_tasks_json` 结构化 JSON（schema_version=1）
- **会话续接** — `context_from` 快照前序任务上下文注入新子代理
- **取消 API** — `cancel_task` 请求式取消 + 2 分钟无更新警告标记
- **输出净化** — label/summary/actions 的 `\n`/`\r`/`|` 清洗 + announce 模板含反注入提示
- **编程代理流式进度** — `_read_stream` 增量 UTF-8 解码 → `TaskStatus.recent_actions`

### Tools

- **统一编程代理** — 自动检测 OpenCode/Codex/Claude Code，6 工具合并为 2（`coding_agent` + `coding_agent_details`）；stale session 自动降级；会话缓存 LRU；优雅进程终止（SIGTERM → 2s → SIGKILL）；默认 30 分钟超时
- **消息工具** — ContextVar 注入 + `reply_to` 透传 + 防重发（空内容拦截 + `_sent_in_turn` 标记）+ 默认拒绝向 desktop channel 发送
- **定时任务工具** — ContextVar 注入 + kwargs-based execute + 输入校验
- **MCP 工具桥接** — Schema 精简（`mcpSlimSchema`）+ 工具总量上限（`mcpMaxTools` + per-server `maxTools`）+ 原子注册回滚 + 连接超时
- **桌面自动化** — 7 个原子工具（screenshot/click/type_text/key_press/scroll/drag/get_screen_info），mss + pyautogui 驱动，Retina/HiDPI 自适应
- **AI 图像生成** — Gemini API 文生图 + 多平台发送
- **Web 工具** — 内容过滤 pipeline + Exa 搜索集成
- **工具输出预算** — artifact pipeline + hard clip
- **工具可观测性** — 每轮 schema 体积采样 + 工具质量代理指标（`tool_selection_hit_rate` / `parameter_fill_success_rate`），软中断调用单独计入

### Providers

- **4 类 Provider** — OpenAI 兼容 / Anthropic / Gemini / OpenAI Codex OAuth
- **Gemini 完全重写** — 用户图片支持（`inline_data` Blob）、流式中断
- **Responses API 自动探测** — OpenAI 兼容端点自动切换 Responses / Chat Completions
- **流式进度回调** — 所有 Provider 统一 `on_progress` / `on_tool_hint` 回调
- **Provider 匹配安全** — 前缀命中要求 type 一致；openai 兜底仅在 type 匹配时生效
- **Anthropic data URL 防御** — 畸形 URL 跳过，不发送空 base64

### Channels

- **9 大平台** — Telegram / Discord / WhatsApp / Feishu / Slack / Email / QQ / DingTalk / iMessage
- **Telegram 媒体组聚合** — `media_group_id` 缓冲 0.6s 窗口后合并发送
- **ProgressBuffer** — iMessage / WhatsApp 非流式渠道缓冲 + 去重 + 边界切分
- **Discord** — RESUME 重连 + zombie 连接检测 + typing loop HTTP 失败隔离
- **Feishu** — thread join + `react_emoji` 可配置
- **iMessage 媒体收发** — AppleScript outbound + attachment 表 inbound + 纯媒体消息占位符
- **渠道双语日志** — gateway / cron / heartbeat / artifacts 全面中英双语

### Config

- **SecretStr 凭据保护** — 所有凭据字段统一 `pydantic.SecretStr`，`model_dump()` 输出 `"**********"`
- **JSONC 加载管线** — 5 状态字符级状态机去注释 → 版本化迁移 → env overlay（`BAO_*` 深度合并）→ Pydantic 验证
- **工具暴露控制** — `toolExposure.mode` 默认 `auto`（智能路由：按需打分曝光 + 自动扩容回退至全量） / `off`（全量暴露）+ `toolExposure.bundles`（core/web/desktop/code）
- **模板 i18n** — workspace 模板按语言存放 `bao/templates/workspace/{zh,en}/`
- **首次引导** — 双语语言选择 + persona 设置 + workspace 模板写入

### Skills

- **17 个内置技能** — 编程代理、图像生成、PDF、DOCX、XLSX、PPTX、浏览器自动化、天气、定时任务等
- **技能摘要压缩** — 单行格式 + 首句或 60 字符截断 + 换行归一化

### Session

- **原子保存** — 写入 + 校验 + rollback，LanceDB 持久化
- **Active Cache** — 内存字典缓存解决 LanceDB 索引延迟
- **会话标题生成** — 首个/第二个 user turn 后异步生成，问候语过滤 + 中文≤12字/英文≤6词约束
- **用户消息即时持久化** — 双层（run 预存 + _process_message 落库），base64 图片剥离

### Desktop App

- **PySide6 + QML 客户端** — 纯 UI 壳子复用 `bao/` core
- **功能** — 聊天界面、设置页、会话管理、侧边栏、Toast 通知
- **JSONC 写回** — `patch_jsonc()` 新增键插入到 `}` 前，避免注释漂移
- **配置保存稳态** — 异常兜底 + `_valid=True` 同步回写

### CLI

- **ASCII art 面包 banner** — rich 渲染（yellow 面包 + bold cyan 文字）
- **友好日志格式** — 彩色 log format

### Gateway

- **共享构建器** — CLI 和 Desktop 复用 `gateway/builder.py`
- **启动问候** — 每渠道独立 LLM 生成，CJK 本地化时间 + 原生语言 trigger，失败回退 `process_direct(ephemeral=True)`

### Bridge

- **WhatsApp 桥接** — TypeScript/Baileys WebSocket 桥接 + 媒体下载

### Infrastructure

- **CI/CD** — `.github/workflows/desktop-release.yml`（macOS arm64/x86_64 + Windows x64 矩阵构建）
- **Docker** — `docker-compose.yml` + `Dockerfile`（Python + Node 混合构建）
- **测试** — 54 个测试文件，pytest + asyncio_mode=auto

[0.3.8]: https://github.com/Suge8/Bao/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/Suge8/Bao/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/Suge8/Bao/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/Suge8/Bao/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/Suge8/Bao/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/Suge8/Bao/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/Suge8/Bao/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/Suge8/Bao/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Suge8/Bao/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Suge8/Bao/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Suge8/Bao/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Suge8/Bao/releases/tag/v0.1.0
[Unreleased]: https://github.com/Suge8/Bao/compare/v0.3.8...HEAD
