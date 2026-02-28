"""Configuration module for bao."""

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
from bao.config.schema import Config

__all__ = [
    "Config",
    "ConfigLoadError",
    "LANG_PICKER",
    "PERSONA_GREETING",
    "detect_onboarding_stage",
    "get_config_path",
    "infer_language",
    "load_config",
    "write_heartbeat",
    "write_instructions",
    "write_persona_profile",
]
