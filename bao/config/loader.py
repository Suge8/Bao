import importlib.resources
import json
from pathlib import Path

from bao.config.paths import get_config_path as resolve_config_path
from bao.config.paths import get_data_dir as resolve_data_dir
from bao.config.paths import set_runtime_config_path
from bao.config.schema import Config
from bao.profile import ensure_profile_registry

from ._loader_helpers import ConfigLoadError as _ConfigLoadError
from ._loader_helpers import (
    apply_env_overlay,
    dump_with_secrets,
    handle_config_error,
    render_commented_jsonc,
    strip_jsonc_comments,
    write_text_atomic,
)

ConfigLoadError = _ConfigLoadError


def get_config_path() -> Path:
    return resolve_config_path()


def get_data_dir() -> Path:
    return resolve_data_dir()


def ensure_first_run() -> bool:
    path = get_config_path()
    if path.exists():
        return False
    config = Config()
    save_config(config)
    _ensure_workspace(config)
    ensure_profile_registry(config.workspace_path)
    return True


def load_config(config_path: Path | None = None) -> Config:
    if config_path is not None:
        set_runtime_config_path(config_path)
    path = config_path or get_config_path()
    if path.exists():
        return _load_existing_config(path)
    ensure_first_run()
    actual = get_config_path()
    print(
        "\n📁 .bao 配置文件夹已创建 / .bao config folder created"
        "\n\n  📝 请编辑文件完成配置 / Please edit to configure:"
        f"\n     {actual}"
        "\n\n  ▶ 然后重新运行 / Then run: bao\n"
    )
    raise SystemExit(0)


def _load_existing_config(path: Path) -> Config:
    from bao.config.migrations import migrate_config as run_migrations

    try:
        text = strip_jsonc_comments(path.read_text(encoding="utf-8"))
        data = json.loads(text)
        migrated, warnings = run_migrations(data)

        # 打印迁移消息并保存更新后的配置
        if warnings:
            for warning in warnings:
                print(f"  ℹ️  {warning}")
            try:
                write_text_atomic(path, render_commented_jsonc(migrated))
            except Exception as e:
                print(f"  ⚠️  无法保存迁移后的配置: {e}")

        overlaid = apply_env_overlay(migrated)
        config = Config.model_validate(overlaid)
        ensure_profile_registry(config.workspace_path)
        return config
    except Exception as error:
        return handle_config_error(path, error)


def save_config(config: Config, config_path: Path | None = None) -> None:
    if config_path is not None:
        set_runtime_config_path(config_path)
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_suffix(".jsonc") if path.suffix != ".jsonc" and not path.exists() else path
    data = dump_with_secrets(config)
    write_text_atomic(target, render_commented_jsonc(data))


def _ensure_workspace(config: Config) -> None:
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    deferred = {"PERSONA.md", "INSTRUCTIONS.md", "HEARTBEAT.md"}
    for item in importlib.resources.files("bao.templates.workspace").iterdir():
        if not item.name.endswith(".md") or item.name in deferred:
            continue
        output_path = workspace / item.name
        if not output_path.exists():
            output_path.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    (workspace / "skills").mkdir(exist_ok=True)
