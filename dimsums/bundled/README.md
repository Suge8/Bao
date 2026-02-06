# bundled dimsums

本目录存放 Bao 内置点心（随桌面应用分发）。

现状（Stage1）：
- provider（openai/anthropic/gemini/xai）已提供可执行 process JSON-RPC 实现。
- skills-adapter 已提供可执行 `resource.list` / `resource.read`。
- mcp-bridge 已提供可执行桥接方法（`bridge.list_tools` / `bridge.call_tool`，支持 stdio/http）。
- router/memory/corrector 仍以 manifest + hook 契约为主，后续继续补齐 wasm 运行实现。

统一约束：
- 所有 process 点心使用 `bao-jsonrpc/v1`。
- 所有执行均受 Bao 权限与审计链约束。
