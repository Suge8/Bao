from __future__ import annotations

from bao.config.migrations import CURRENT_VERSION, migrate_config


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
