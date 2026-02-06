# 当前进度

- Bundled dimsums 已具备目录与可执行 process 配置：router/memory/corrector/mcp-bridge/skills-adapter/providers。
- skills 资源工具 schema 与运行链路已落地：resource.list/resource.read。
- gateway/plugin-host 从接口 stub 进入可运行阶段（握手/缓存/实例池 + process runner）。

# 改动记录（最近）

- [FEAT] 2026-02-05 增加 bundled providers（OpenAI/Anthropic/Gemini/xAI）manifest stubs
- [FEAT] 2026-02-05 细化 bao-gateway 与 bao-plugin-host 接口 stubs（握手/缓存/实例池）

# 未来发展（优先级）

P0

- ✅ 已完成（2026-02-06）：gateway V1 握手与帧格式 schemas（hello/welcome/event/replay）已落地并加入验证。
- ✅ 已完成（2026-02-06）：plugin-host process runner 已支持超时/输出/kill-group，错误可观测写入链路已具备。

P1

- ✅ 已完成（2026-02-06）：providers JSON-RPC 协议 schemas + 最小 smoke/语义测试已覆盖。
