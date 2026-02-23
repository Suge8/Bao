"""Configuration module for bao."""

from bao.config.loader import load_config, get_config_path
from bao.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
