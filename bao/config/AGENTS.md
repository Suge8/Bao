# bao/config/ — 配置系统

## 🔴 最高优先设计原则（必须遵守）

- 先设计单一路径，再实现；禁止事后叠加控制修补竞态。
- 不增加状态机/定时器/分支前，先删除重复入口，保证一个事实源和一个触发点。
- 优先消除中间态可见性（避免“先到顶部再回底部”），不要靠补丁式回滚逻辑。
- 稳定性修复必须做“减控制审查”：能删则删，保留最小可用控制面。

配置子域独立于业务逻辑，负责 schema、加载、迁移、首次引导。

## OVERVIEW

- 高风险链路：`loader.py` 的加载顺序 + `migrations.py` 的版本演进 + `schema.py` 的兼容策略。

## STRUCTURE

| 文件 | 作用 | 风险点 |
|------|------|--------|
| `schema.py` | Pydantic 配置模型与约束 | 字段变更影响全局启动和校验；渠道 `group_policy`、`agents.defaults.reasoningEffort` 与 `agents.defaults.serviceTier` 都在这里定义 |
| `loader.py` | JSONC 读取/去注释/迁移/env overlay/验证 | 顺序被改会破坏兼容性 |
| `migrations.py` | `config_version` 迁移链 | 升级逻辑不幂等会损坏旧配置 |
| `onboarding.py` | 首次引导与 workspace 模板写入 | 模板与语言分支需一致 |

## WHERE TO LOOK

| 任务 | 位置 | 备注 |
|------|------|------|
| 新增配置项 | `schema.py` + `loader.py` | 字段、默认值、序列化统一更新；策略类字段优先复用已有 schema 结构 |
| 版本升级 | `migrations.py` | 只做 `vN -> vN+1` 纯函数迁移 |
| env 覆盖策略 | `loader.py:_apply_env_overlay` | `BAO_*` + `__` 分层映射 |
| 首次模板变更 | `onboarding.py` + `bao/templates/workspace/*` | 保持 zh/en 对齐 |

## CONVENTIONS

- 加载顺序固定：read -> strip comments -> migrate -> env overlay -> validate。
- 策略字段遵循 warn-but-don't-reject，不因未知值直接拒绝配置。
- OpenAI-family 的生成参数统一从 `AgentDefaults` 下发：`reasoning_effort` 控制推理深度，`service_tier` 控制官方服务档位；配置层不再引入第二套 fastmode 别名。
- 渠道组策略字段（如 Telegram/Discord/Feishu 的 `group_policy`）保持统一字面值集合与一致默认值，避免同类配置出现结构变体。
- MCP transport 通过 `MCPServerConfig.type` 显式声明或从 `command/url` 推断，配置层不再引入第二套 transport schema。
- 凭据字段统一 `SecretStr`，访问必须 `.get_secret_value()`。
- 迁移代码保持防御式：输入类型异常不崩溃，返回 warning。

## ANTI-PATTERNS

- 不要在其他目录绕过 `loader.py` 直接解析配置文件。
- 不要在迁移中做跨文件副作用或网络调用。
- 不要在 `schema.py` 引入与配置无关的业务逻辑。
