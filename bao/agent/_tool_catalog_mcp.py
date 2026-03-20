from __future__ import annotations

from bao.agent._tool_catalog_common import (
    as_dict,
    as_list,
    as_str,
    attention_status,
    get_path,
    localized,
    mcp_status,
    mcp_transport,
    non_bool_int,
)


def build_mcp_server_items(
    config_data: dict[str, object],
    probe_results: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    server_map = as_dict(get_path(config_data, "tools.mcpServers", {})) or {}
    return [
        _build_mcp_item(name, as_dict(raw_value) or {}, probe_results.get(name, {}))
        for name, raw_value in server_map.items()
    ]


def _build_mcp_item(
    name: str,
    server_cfg: dict[str, object],
    probe: dict[str, object],
) -> dict[str, object]:
    probe_tool_names = [str(item) for item in (as_list(probe.get("toolNames")) or [])]
    command = as_str(server_cfg.get("command", ""))
    url = as_str(server_cfg.get("url", ""))
    args = [str(item) for item in (as_list(server_cfg.get("args")) or [])]
    env = {str(k): str(v) for k, v in (as_dict(server_cfg.get("env")) or {}).items()}
    headers = {str(k): str(v) for k, v in (as_dict(server_cfg.get("headers")) or {}).items()}
    transport = mcp_transport(command, url)
    status, status_label, status_detail, status_detail_display = mcp_status(
        transport=transport,
        probe=probe,
        tool_count=len(probe_tool_names),
    )
    return {
        "id": f"mcp:{name}",
        "kind": "mcp_server",
        "source": "mcp",
        "name": name,
        "displayName": localized(name, name),
        "bundle": "mcp",
        "summary": "External MCP server definition.",
        "displaySummary": localized("外部 MCP 服务定义。", "External MCP server definition."),
        "detail": "MCP servers expand into runtime tools after a successful handshake.",
        "displayDetail": localized("MCP 服务在握手成功后会展开为运行时工具。", "MCP servers expand into runtime tools after a successful handshake."),
        "capabilities": [transport.upper() if transport != "unconfigured" else "Setup", "External", "MCP"],
        "includedTools": probe_tool_names,
        "status": status,
        "statusLabel": status_label,
        "statusDetail": status_detail,
        "statusDetailDisplay": status_detail_display,
        "needsAttention": attention_status(status),
        "formKind": "mcp_server",
        "configValues": {
            "previousName": name,
            "name": name,
            "transport": transport,
            "command": command,
            "argsText": "\n".join(args),
            "envText": "\n".join(f"{key}={value}" for key, value in env.items()),
            "url": url,
            "headersText": "\n".join(f"{key}: {value}" for key, value in headers.items()),
            "toolTimeoutSeconds": non_bool_int(server_cfg.get("toolTimeoutSeconds"), 30),
            "maxTools": non_bool_int(server_cfg.get("maxTools"), 0),
            "slimSchema": server_cfg.get("slimSchema"),
        },
        "iconSource": "../resources/icons/sidebar-tools.svg",
        "metaLines": [
            f"Transport: {transport}",
            f"Timeout: {non_bool_int(server_cfg.get('toolTimeoutSeconds'), 30)}s",
        ],
        "probe": dict(probe),
        "searchText": " ".join([name, transport, command, url, "mcp", *probe_tool_names]).lower(),
    }
