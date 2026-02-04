# Bao — PRD（世界级桌面 Agent 框架与应用）

## 1. 产品定位

Bao 是一个世界级的本地桌面 Agent 应用与框架：  
用户只需安装并打开桌面应用，即获得：

- 对话式 Agent
- 可扩展点心（工具/路由/记忆/校验/供应商适配）
- 任务与提醒（含周期任务/心跳任务：持续开发与自我进化）
- 可检索的聊天记录与原生记忆系统（Progressive Disclosure + Evolution Pipeline）
- 不可篡改审计日志

桌面应用运行即是网关：一个或多个移动端在同局域网可连接桌面，远程对话与管理；远程场景推荐使用 Tailscale / tunnel，将本地网关安全暴露到远端。  
唯一桌面入口：不提供 Web 面板。

---

## 2. 目标用户

- 普通用户（C 端）：需要“快、轻、智能”，不愿运行命令行服务
- 进阶用户/开发者：需要插件生态、可热更新、可接入 MCP/外部 CLI（claudecode/codex 等），并可用手机远程操控电脑完成操作
- 社区贡献者：希望独立开发点心，发布并被用户安装

---

## 3. 核心差异化（必须做到）

- 点心热拔插生态
- Router/Memory/Corrector/Provider 也都是点心（内置点心分发）
- 社区点心可独立迭代，不影响 core 稳定
- 确定性工具调用
- 必触发必须可验证（quote 必须命中当前 user message）
- 禁止自然话+JSON 执行工具
- 资源型 skills 适配
- skills 不只 prompt：可包含代码/CSV/模板/图片
- Bao 必须确定性处理：SKILL.md 为 prompt，其余文件为资源（只读，不自动执行）
- 世界级 UI/UX
- 现代美观、动效丰富、信息架构稳定
- 桌面唯一入口，所有能力可视化管理
- 审计与安全
- 重要操作可追溯（audit hash chain）
- 权限门禁明确（fs/cmd/desktop/browser/net 等）
- 原生记忆系统（世界级体验）
- Single Source of Truth（SQLite+Blob）
- Progressive Disclosure（三段式检索注入）
- Memory Evolution Pipeline（抽取→去重→冲突→合并→版本化）
- 透明、可控、可撤销（证据链+版本历史+回滚）
- 持续执行能力（心跳/周期任务）
- 可用手机/桌面创建周期任务：持续开发项目、周期性自我进化、定期回归
- 任务执行同样受权限与审计约束，支持 Kill Switch

---

## 4. 桌面 UI 规范（固定，不允许自由发挥）

### 4.1 技术栈（固定）

- React + Vite
- shadcn/ui（基础组件）+ magicui（美化外观）
- packages/baseui（Bao 自建统一组件层：统一视觉/交互/动效封装）
- framer-motion（动效必须覆盖全站）
- i18n：zh-CN + en-US 内置；localepack 点心可增加其他语言

### 4.2 顶层布局（固定）

**左侧 Sidebar（主导航，icon+label，可折叠）**

- Chat（主页）
- Tasks
- Dimsums
- Memory
- Settings（内部含 Logs）

**顶部 Topbar（固定高度）**

- 当前会话标题（可编辑）
- Gateway 状态：未开启/仅本机/局域网开放 + 已连接设备数
- 当前 Provider/Model
- 快捷按钮：新会话 / 暂停执行 / 紧急停止（Kill Switch）

**主内容区（按页面切换）**

- 页面切换必须有 framer-motion 动画（200ms）

### 4.3 Chat 页面（三段式，固定）

**左：会话列表**

- 搜索框（FTS）
- 新建会话
- 会话分组：最近/任务/系统

**中：消息流**

- 虚拟列表（性能必须好）
- streaming 渲染（delta -> done）
- assistant 消息支持：Markdown、代码块、工具卡片摘要

**右：Inspector（可折叠）**

- 当前消息的 tool calls（参数/结果/耗时）
- memory inject 预览（本轮注入了哪些；默认 hits/snippets，必要时少量全文）
- task 状态（由本轮创建/更新，或由 Scheduler 触发）
- 原始事件流（debug）

**动效要求（Chat）**

- 新消息进入：fade+slide
- tool 卡片展开/收起：height 动画
- Inspector 开合：侧滑动画
- 会话切换：消息列表 crossfade

### 4.4 Tasks 页面（固定）

- 列表：提醒/循环任务/cron/心跳任务

**创建任务**

- 类型：一次性提醒 / 循环提醒 / cron / 高级（绑定 dimsum tool）
- 输入：时间/周期/cron/内容（高级：dimsumId+toolName+args）

**任务执行记录**

- 最近 N 次运行（来自 events/tool_calls/audit_events）

**任务控制**

- 启用/禁用
- 立即运行（run-now）
- Kill Switch（终止正在运行的任务/工具）

### 4.5 Dimsums 页面（固定）

**Installed 列表**

- 名称/版本/作者/类型（tool/pipeline/provider/promptpack/resourcepack/localepack/bridge）
- 启用/禁用（bundled 点心不可卸载）
- 权限申请展示与用户授权状态

**详情页**

- manifest 展示
- tools 列表（schema/timeout/cache/idempotency）
- pipeline hooks 列表
- resources 浏览（skills 的 py/csv/template 预览）
- 更新按钮（community/local 可更新；bundled 仅随 app 更新）
- 自我进化状态（若安装 autoevolve：展示回归结果/最近升级/回滚记录）

### 4.6 Memory 页面（固定；必须体现 Progressive Disclosure + Evolution Pipeline）

- 结构化记忆列表（memory_items）
- 默认只显示 hits：title/snippet/score/tags/status
- 支持按 namespace/kind/tag/status 过滤
- 搜索（FTS + hybrid rank 的结果展示可解释）

**详情页（三段式信息透明）**

- 正文（content/json）
- 证据链（memory_links：来自哪些 message/event/artifact）
- 版本历史（memory_versions：可回滚到某版本）
- 编辑/删除（确认弹窗）
- 回滚（需要确认；写 audit；回滚后产生新版本）
- 记忆注入统计：score/injectCount/lastInjectedAt

### 4.7 Settings 页面（固定子菜单）

Settings 内部固定四个子页：

- Providers & Models
- Permissions
- Devices
- Logs

**Providers & Models**

- 列表：OpenAI / Anthropic / Gemini / xAI
- 字段：BaseURL（可空）、API Key、默认模型、备用模型
- 保存后写入 settings 表并写入 audit

**Permissions**

- 开关列表（来自 permissions_v1.json）
- 每次变更写 audit

**Devices**

- 生成配对二维码（token）
- 已连接设备列表：deviceId/平台/最近活跃
- 一键断开（revocation）
- 远程提示：推荐使用 Tailscale / tunnel；默认仅监听 127.0.0.1，不建议公网暴露

**Logs**

- 审计日志（audit_events）分页 + 实时追加
- 支持按 action/type 过滤

---

## 5. i18n 规范（固定）

- 内置语言：zh-CN、en-US

i18n keys 固定命名：

- nav.chat, nav.tasks, ...
- settings.providers, ...

localepack 点心可新增语言：

- 在 manifest.locales 声明 locale 与 path
- 桌面启动时加载并加入语言选择列表

任何新增 UI 文案必须走 i18n key。

---

## 6. 点心体系（产品级要求）

### 6.1 内置点心（Bundled Dimsums）

随应用分发、不可卸载、由官方维护版本：

- Router（pipeline）
- Memory（pipeline + tools：三段式检索与变更计划）
- Corrector（pipeline）
- Providers：OpenAI/Anthropic/Gemini（provider）
- skills-adapter（promptpack+resourcepack）
- mcp-bridge（tool+bridge，runtime=process）
- pty（tool，runtime=process）
- autoevolve（tool：自我进化计划/回归/升级/回滚；默认不开启周期执行，需用户创建任务并授权）

### 6.2 skills 边缘情况处理（强约束）

skills repo 内文件分类规则固定：

- SKILL.md → prompt + metadata
- 其他全部 → resources（text/binary）

资源读取：

- 只能通过工具：resource.list/resource.read
- 受 fs.read 权限门禁

代码执行：

- 绝不自动执行
- 执行必须通过 PTY/CLI 工具，受 cmd.exec 权限门禁，并写入 audit

### 6.3 MCP 适配（强约束）

- MCP 接入只通过 mcp-bridge 点心实现
- mcp-bridge 将 MCP tools 映射为 Bao tools
- 执行仍受 Bao 权限门禁（MCP server 不可越权）

### 6.4 WASM 性能策略（强约束）

- Module cache：按 sha256 复用 compiled module
- Instance pool：highFrequency 固定 warm=2
- lowFrequency：调用即建、结束即毁

Limits：

- maxLinearMemoryBytes
- fuelPerCall
- timeoutMs

任何越界必须中止并返回明确错误事件（写入 audit）。

### 6.5 Memory Native（强约束）

- 存储：SQLite + Blob（真相）
- 索引：FTS5（硬召回） + Vector（软召回，可插拔）
- 检索注入：Progressive Disclosure（三段式）
- 写入演化：Extract→Dedup→Merge→Versioned Mutations
- 扩展：点心只能提交 mutation 计划，core 统一执行审计/回滚
- UI：透明、可控、可撤销（证据链+版本历史+回滚）

### 6.6 Scheduler/Heartbeat（强约束）

- Scheduler 是 core 能力，心跳驱动
- 周期任务是“显式 dimsum tool call”，不得隐式推断
- 自我进化必须回归通过才升级，失败回滚
- Kill Switch 必须可终止正在执行的任务/工具

---

## 7. 安全与审计（必须）

所有以下行为必须写入 audit_events（hash chain）：

- 权限开关变化
- provider/model 配置变化
- 点心安装/更新/启用/禁用
- 工具调用（含参数与结果摘要）
- 记忆变更（新增/更新/删除/回滚；含版本与证据链）
- 任务创建/触发/完成/失败/终止

Kill Switch（紧急停止）必须在桌面 UI 顶部可达，并能终止正在运行的工具/点心调用/任务执行。

---

## 8. 性能指标（必须）

- 桌面冷启动首屏可交互 <= 1000ms
- Router hook <= 30ms
- 单工具超时 <= 1000ms；最多重试 1 次
- UI 滚动与渲染不卡顿（消息列表虚拟化必须实现）
- Memory 检索默认只取 hits/snippets（Progressive Disclosure），避免上下文污染

---

## 9. 交付范围（V1 必做）

- 桌面端全功能 UI（Chat/Tasks/Dimsums/Memory/Settings+Logs）
- 内置点心全部可用（含 memory 与 autoevolve 工具）
- Gateway + 移动端最小可用（连接/收发消息/事件渲染）
- schema 校验与最小回归测试集可运行（含 memory 与 scheduler 回归）
