# bao.bundled.corrector

内置 Corrector 点心（pipeline）。

当前阶段（Stage1）已提供可执行 JSON-RPC 服务：
- `corrector.methods`
- `corrector.validate_tool_args`
- `corrector.validate_tool_result`
- `corrector.decide_retry`

开发环境运行命令：
- `cargo run -q -p bao-dimsum-process --bin bao-corrector-hook --`
