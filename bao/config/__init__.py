"""Configuration module for Bao."""

from bao.config.loader import ConfigLoadError, get_config_path, load_config
from bao.config.onboarding import (
    LANG_PICKER,
    PERSONA_GREETING,
    detect_onboarding_stage,
    infer_language,
    write_heartbeat,
    write_instructions,
    write_persona_profile,
)
from bao.config.paths import (
    get_bridge_install_dir,
    get_cli_history_path,
    get_data_dir,
    get_legacy_sessions_dir,
    get_media_dir,
    get_runtime_subdir,
    get_workspace_path,
    set_runtime_config_path,
)
from bao.config.schema import Config

__all__ = [
    "Config",
    "ConfigLoadError",
    "LANG_PICKER",
    "PERSONA_GREETING",
    "detect_onboarding_stage",
    "get_config_path",
    "get_data_dir",
    "get_runtime_subdir",
    "get_media_dir",
    "get_workspace_path",
    "get_cli_history_path",
    "get_bridge_install_dir",
    "get_legacy_sessions_dir",
    "infer_language",
    "load_config",
    "set_runtime_config_path",
    "write_heartbeat",
    "write_instructions",
    "write_persona_profile",
]
