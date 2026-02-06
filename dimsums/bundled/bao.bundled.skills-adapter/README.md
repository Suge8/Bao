# bao.bundled.skills-adapter

内置 skills 资源适配点心（`types: ["promptpack", "resourcepack", "tool"]`，`runtime: process`）。

当前阶段（Stage1）已提供可执行 JSON-RPC 服务：
- `resource.methods`
- `resource.list`
- `resource.read`

开发环境运行命令：
- `cargo run -q -p bao-dimsum-process --bin bao-skills-adapter --`

命名空间：
- `skills`：默认 `BAO_SKILLS_ROOT`，回退 `~/.agents/skills`
- `dir:<abs_path>`：显式目录（仅开发）
