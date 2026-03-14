from __future__ import annotations

from bao.config.migrations import CURRENT_VERSION, migrate_config
from bao.config.schema import Config


def test_migrate_v2_adds_tool_exposure_defaults() -> None:
    data = {
        "config_version": 2,
        "tools": {
            "exec": {"timeout": 60},
        },
    }
    migrated, _ = migrate_config(data)
    assert migrated["config_version"] == CURRENT_VERSION
    assert migrated["tools"]["toolExposure"]["mode"] == "auto"
    assert migrated["tools"]["toolExposure"]["bundles"] == ["core", "web", "desktop", "code"]


def test_migrate_v0_handles_non_dict_web_config() -> None:
    data = {
        "config_version": 0,
        "tools": {
            "web": "invalid",
        },
    }
    migrated, warnings = migrate_config(data)
    assert migrated["config_version"] == CURRENT_VERSION
    assert isinstance(warnings, list)


def test_migrate_warnings_include_each_applied_step() -> None:
    data = {"config_version": 1, "tools": {}}
    _, warnings = migrate_config(data)
    assert "Migrated config v1 → v2" in warnings
    assert "Migrated config v2 → v3" in warnings
    assert "Migrated config v3 → v4" in warnings


def test_migrate_v3_moves_legacy_memory_fields_under_memory_block() -> None:
    data = {
        "config_version": 3,
        "agents": {
            "defaults": {
                "memoryWindow": 42,
                "experienceModel": "main",
            }
        },
    }

    migrated, _ = migrate_config(data)

    defaults = migrated["agents"]["defaults"]
    assert defaults["memory"]["recentWindow"] == 42
    assert defaults["memory"]["learningMode"] == "main"
    assert "memoryWindow" not in defaults
    assert "experienceModel" not in defaults


def test_nested_memory_settings_override_legacy_fields_during_validation() -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "memoryWindow": 12,
                    "experienceModel": "utility",
                    "memory": {
                        "recentWindow": 64,
                        "learningMode": "main",
                    },
                }
            }
        }
    )

    assert config.agents.defaults.memory.recent_window == 64
    assert config.agents.defaults.memory.learning_mode == "main"
    assert config.agents.defaults.memory_window == 64
    assert config.agents.defaults.experience_model == "main"
