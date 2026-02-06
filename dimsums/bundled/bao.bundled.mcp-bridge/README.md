# bao.bundled.mcp-bridge

内置 MCP Bridge 点心（`types: ["tool", "bridge"]`，`runtime: process`）。

当前阶段（Stage1）提供可运行 JSON-RPC 服务：
- `bridge.methods`
- `bridge.ping`
- `bridge.list_tools`
- `bridge.call_tool`

支持传输：
- `stdio`：启动 MCP server 进程，完成 `initialize` 握手后执行 `tools/list` / `tools/call`
- `http`：按 JSON-RPC 透传 `tools/list` / `tools/call`

开发环境运行命令：
- `cargo run -q -p bao-dimsum-process --bin bao-mcp-bridge --`
