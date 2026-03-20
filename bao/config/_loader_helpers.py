"""Pure helper functions for config loading and persistence."""

import copy
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.config._loader_template import JSONC_TEMPLATE
from bao.config.schema import Config

NORMAL, IN_STRING, ESCAPE, LINE_COMMENT, BLOCK_COMMENT = range(5)


class ConfigLoadError(Exception):
    """Raised when config file exists but cannot be parsed/validated."""


def handle_config_error(path: Path, error: Exception) -> Config:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".broken.{ts}{path.suffix}")
    try:
        shutil.copy2(path, backup)
    except OSError:
        backup = None
    parts = ["", "❌ 配置文件有误 / Config file error", "", f"   📄 文件 File: {path}"]
    append_error_detail(parts, path, error)
    if backup:
        parts.append(f"   💾 已备份 Backup: {backup}")
    parts.append("")
    if os.environ.get("BAO_CONFIG_STRICT", "1") != "0":
        parts.extend(
            [
                "   💡 修复后重新运行 / Fix and re-run: bao",
                "   💡 或跳过检查 / Or skip: BAO_CONFIG_STRICT=0 bao",
                "",
            ]
        )
        print("\n".join(parts))
        raise SystemExit(1)
    parts.extend(["   ⚡ BAO_CONFIG_STRICT=0 → 使用默认配置继续 / Using defaults", ""])
    print("\n".join(parts))
    return Config()


def append_error_detail(parts: list[str], path: Path, error: Exception) -> None:
    if not isinstance(error, json.JSONDecodeError):
        parts.append(f"   💬 原因 Reason: {error}")
        return
    parts.append(
        f"   📍 位置 Location: 第 {error.lineno} 行, 第 {error.colno} 列"
        f" / line {error.lineno}, col {error.colno}"
    )
    parts.append(f"   💬 原因 Reason: {error.msg}")
    try:
        append_json_context(parts, path, lineno=error.lineno)
    except OSError:
        return


def append_json_context(parts: list[str], path: Path, *, lineno: int) -> None:
    src = path.read_text(encoding="utf-8").splitlines()
    start = max(0, lineno - 3)
    end = min(len(src), lineno)
    if start >= end:
        return
    parts.append("")
    for index in range(start, end):
        line_number = index + 1
        marker = " 👉" if line_number == lineno else "   "
        parts.append(f"  {marker} {line_number:>4} | {src[index]}")


def apply_env_overlay(data: dict[str, Any]) -> dict[str, Any]:
    from pydantic.alias_generators import to_camel

    for key, value in os.environ.items():
        if not key.startswith("BAO_"):
            continue
        parts = key[len("BAO_") :].lower().split("__")
        if not parts or not parts[-1]:
            continue
        target = data
        for part in parts[:-1]:
            target = ensure_overlay_branch(target, part, to_camel(part))
        leaf = to_camel(parts[-1])
        if leaf not in target and parts[-1] in target:
            leaf = parts[-1]
        target[leaf] = parse_env_overlay_value(value)
    return data


def ensure_overlay_branch(target: dict[str, Any], part: str, camel: str) -> dict[str, Any]:
    if camel in target and isinstance(target[camel], dict):
        return target[camel]
    if part in target and isinstance(target[part], dict):
        return target[part]
    target[camel] = {}
    return target[camel]


def parse_env_overlay_value(value: str) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def strip_jsonc_comments(text: str) -> str:
    state = NORMAL
    block_depth = 0
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == NORMAL:
            if char == '"':
                out.append(char)
                state = IN_STRING
                index += 1
                continue
            if char == "/" and nxt == "/":
                state = LINE_COMMENT
                index += 2
                continue
            if char == "/" and nxt == "*":
                state = BLOCK_COMMENT
                block_depth = 1
                index += 2
                continue
            out.append(char)
            index += 1
            continue
        if state == IN_STRING:
            out.append(char)
            state = ESCAPE if char == "\\" else NORMAL if char == '"' else IN_STRING
            index += 1
            continue
        if state == ESCAPE:
            out.append(char)
            state = IN_STRING
            index += 1
            continue
        if state == LINE_COMMENT:
            if char == "\n":
                out.append(char)
                state = NORMAL
            index += 1
            continue
        if char == "/" and nxt == "*":
            block_depth += 1
            index += 2
            continue
        if char == "*" and nxt == "/":
            block_depth -= 1
            index += 2
            state = NORMAL if block_depth == 0 else BLOCK_COMMENT
            continue
        index += 1
    if state == BLOCK_COMMENT or block_depth != 0:
        raise ValueError("Unterminated block comment in config file")
    return "".join(out)


def flatten_json_leaf_paths(data: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(data, dict):
        if not data:
            return {prefix: {}}
        flattened: dict[str, Any] = {}
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(flatten_json_leaf_paths(value, next_prefix))
        return flattened
    return {prefix: data}


def collapse_missing_intermediates(
    data: dict[str, Any],
    changes: dict[str, Any],
) -> dict[str, Any]:
    passthrough: dict[str, Any] = {}
    needs_collapse: dict[str, dict[str, Any]] = {}
    for dotpath, value in changes.items():
        parts = dotpath.split(".")
        if len(parts) < 2:
            passthrough[dotpath] = value
            continue
        node: Any = data
        depth = 0
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                break
            node = node[part]
            depth += 1
        if depth == len(parts) - 1:
            passthrough[dotpath] = value
            continue
        collapse_key = ".".join(parts[: depth + 1])
        leaf_key = ".".join(parts[depth + 1 :])
        needs_collapse.setdefault(collapse_key, {})[leaf_key] = value

    for collapse_key, flat_leaves in needs_collapse.items():
        obj: dict[str, Any] = {}
        for leaf_path, value in flat_leaves.items():
            leaf_parts = leaf_path.split(".")
            target = obj
            for key in leaf_parts[:-1]:
                nested = target.get(key)
                if not isinstance(nested, dict):
                    nested = {}
                    target[key] = nested
                target = nested
            target[leaf_parts[-1]] = value
        passthrough[collapse_key] = obj
    return passthrough


def write_text_atomic(path: Path, content: str) -> None:
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def sanitize_persisted_config_data(data: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(data)
    _prune_legacy_agent_fields(payload)
    _prune_provider_noise(payload)
    _prune_disabled_channel_noise(payload)
    return payload


def _prune_legacy_agent_fields(data: dict[str, Any]) -> None:
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return
    defaults = agents.get("defaults")
    if not isinstance(defaults, dict):
        return
    defaults.pop("experienceModel", None)
    defaults.pop("memoryWindow", None)


def _prune_provider_noise(data: dict[str, Any]) -> None:
    providers = data.get("providers")
    if not isinstance(providers, dict):
        return
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        if provider.get("type") == "openai":
            provider.pop("type", None)
        if provider.get("extraHeaders") == {}:
            provider.pop("extraHeaders", None)


def _prune_disabled_channel_noise(data: dict[str, Any]) -> None:
    channels = data.get("channels")
    if not isinstance(channels, dict):
        return
    for channel in channels.values():
        if not isinstance(channel, dict) or channel.get("enabled", False) is True:
            continue
        for key in list(channel.keys()):
            if key == "enabled":
                continue
            value = channel.get(key)
            if value in ("", [], {}):
                channel.pop(key, None)


def render_commented_jsonc(data: dict[str, Any]) -> str:
    from app.backend._config_common import _inject_provider_comments
    from app.backend.jsonc_patch import patch_jsonc

    template_text = JSONC_TEMPLATE
    template_data = json.loads(strip_jsonc_comments(template_text))
    changes = flatten_json_leaf_paths(sanitize_persisted_config_data(data))
    collapsed = collapse_missing_intermediates(template_data, changes)
    rendered, errors = patch_jsonc(template_text, collapsed)
    if errors:
        messages = "; ".join(error.message for error in errors)
        raise ValueError(f"Failed to render JSONC config: {messages}")
    rendered = _inject_provider_comments(rendered)
    json.loads(strip_jsonc_comments(rendered))
    return rendered




def dump_with_secrets(config: Config) -> dict[str, Any]:
    from pydantic import BaseModel, SecretStr

    def walk(obj: Any) -> Any:
        if isinstance(obj, SecretStr):
            return obj.get_secret_value()
        if isinstance(obj, BaseModel):
            data = obj.model_dump(by_alias=True, exclude_defaults=True)
            for field_name, field_info in type(obj).model_fields.items():
                value = getattr(obj, field_name)
                if isinstance(value, (SecretStr, BaseModel, dict)):
                    key = resolve_dump_key(obj, field_name, field_info.alias)
                    if key in data:
                        data[key] = walk(value)
            return data
        if isinstance(obj, dict):
            return {key: walk(value) for key, value in obj.items()}
        return obj

    return walk(config)


def resolve_dump_key(obj: Any, field_name: str, alias: str | None) -> str:
    key = alias or field_name
    if key in obj.model_dump(by_alias=True):
        return key
    model_config = getattr(obj, "model_config", {})
    alias_generator = model_config.get("alias_generator") if hasattr(model_config, "get") else None
    generated = call_alias_generator(alias_generator, field_name)
    return generated or field_name


def call_alias_generator(alias_generator: Any, field_name: str) -> str | None:
    if callable(alias_generator):
        generated = alias_generator(field_name)
        return generated if isinstance(generated, str) else None
    alias_fn = getattr(alias_generator, "alias", None)
    if callable(alias_fn):
        generated = alias_fn(field_name)
        return generated if isinstance(generated, str) else None
    return None
