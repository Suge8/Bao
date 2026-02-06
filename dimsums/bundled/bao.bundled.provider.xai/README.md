# bao.bundled.provider.xai

内置 xAI Provider 点心（`types: ["provider"]`，`runtime: process`）。

当前阶段（Stage1）已提供可执行 JSON-RPC 服务：
- `provider.methods`
- `provider.run`
- `provider.cancel`

开发环境运行命令：
- `cargo run -q -p bao-dimsum-process --bin bao-provider-xai --`

鉴权支持：
- 优先 `config.apiKey`
- 回退 `XAI_API_KEY` / `BAO_PROVIDER_API_KEY`
