# docs/ — 文档运维域

该目录不是普通说明集合，包含同步工作流、消息策略契约与打包发布手册。

## OVERVIEW

- 文档更新必须可执行、可审计，且与当前代码行为一致。

## WHERE TO LOOK

| 任务 | 位置 | 备注 |
|------|------|------|
| 发布 checklist | `release-checklist.md` | 发版统一入口，只保留步骤编排并引用专项文档 |
| 上游同步流程 | `update.md` | 检查点、保护文件、禁用操作、记录模板 |
| 消息策略契约 | `messaging-policy.md` | 非流式通道行为与边界切分规则 |
| 工具暴露策略评测 | `tool-exposure-evolution.md` + `tool-exposure-cases.json` | `toolExposure` 行为回归与案例基线 |
| Desktop 打包 | `desktop-packaging.md` | PyInstaller 主链、Nuitka 备用链、平台差异与 workaround |
| PyPI 发布 | `pypi-release.md` | PyPI 环境准备、发布与失败信号 |
| Desktop 产品约束 | `prd-desktop-app.md` | 目标范围与架构边界 |

## CONVENTIONS

- 变更命令、路径、配置项时，文档要同 PR 同步更新。
- 新增或调整公开配置项时，README 与对应子域 AGENTS 要同步说明真实字段名与支持范围，避免 UI 文案、配置模板和实现漂移。
- 流程文档优先写“可执行步骤 + 失败信号”，避免空泛描述。
- 对外声明的行为必须能在代码中定位到实现路径。
- 遇到版本、发版、tag、Release asset 相关任务，先读 `release-checklist.md`，再按需进入 `pypi-release.md` 或 `desktop-packaging.md`。
- 遇到“原子提交 + 版本升级”类提示词时，要在文档中明确执行顺序，避免把提交范围误缩到版本文件。

## ANTI-PATTERNS

- 不要复制粘贴过期命令或历史检查点。
- 不要在文档中引导破坏性 git 操作。
- 不要让策略文档与当前实现长期漂移。
