# 当前进度

- Bundled dimsums 已具备目录与 manifest stub：router/memory/corrector/mcp-bridge/skills-adapter/providers。
- skills 资源工具 schema 已落盘：resource.list/resource.read。
- gateway/plugin-host 的接口 stubs 已细化到握手/缓存/实例池层面。

# 改动记录（最近）

- [FEAT] 2026-02-05 增加 bundled providers（OpenAI/Anthropic/Gemini/xAI）manifest stubs
- [FEAT] 2026-02-05 细化 bao-gateway 与 bao-plugin-host 接口 stubs（握手/缓存/实例池）

# 未来发展（优先级）

P0

- 为 gateway 增加 V1 握手与帧格式 schemas（hello/welcome/event/replay）并加入 schema-tests。
- 为 plugin-host 增加 wasmtime 约束映射接口（fuel/memory/epoch timeout）与错误类型 IR（写入 audit）。

P1

- providers 的 JSON-RPC 协议 schemas + 最小 smoke tests。
