# ruff: noqa: E402, N802, N815
from __future__ import annotations

from pathlib import Path

from tests._profile_supervisor_service_harness import build_supervisor
from tests._profile_supervisor_service_testkit import model_items, wait_until

pytest_plugins = ("tests._profile_supervisor_service_testkit",)


def test_supervisor_hides_live_work_when_hub_is_not_running(tmp_path: Path, qt_app, fake_home: Path) -> None:
    _ = qt_app
    _ = fake_home
    harness = build_supervisor(tmp_path)
    try:
        harness.chat_service.state = "stopped"
        harness.chat_service.hubState = "idle"
        harness.supervisor.refresh()
        wait_until(lambda: harness.supervisor.overview.get("profileCount") == 2)
        harness.supervisor.selectProfile("default")
        wait_until(lambda: harness.supervisor.selectedProfile.get("id") == "default")
        assert harness.supervisor.selectedProfile["isHubLive"] is False
        assert harness.supervisor.selectedProfile["workingCount"] == 0
        assert model_items(harness.supervisor.workingModel) == []
    finally:
        harness.runner.shutdown(grace_s=1.0)


def test_supervisor_formats_automation_time_as_relative_label(tmp_path: Path, qt_app, fake_home: Path) -> None:
    _ = qt_app
    _ = fake_home
    harness = build_supervisor(tmp_path)
    try:
        harness.supervisor.refresh()
        wait_until(lambda: harness.supervisor.overview.get("profileCount") == 2)
        cron_item = next(
            item
            for item in model_items(harness.supervisor.automationModel)
            if str(item.get("routeKind", "")) == "cron" and str(item.get("profileId", "")) == "default"
        )
        label = str(cron_item.get("updatedLabel", ""))
        assert "2026" not in label
        assert label.endswith(("前", "后")) or label == "刚刚"
    finally:
        harness.runner.shutdown(grace_s=1.0)


def test_supervisor_select_profile_emits_filtered_collections_immediately(tmp_path: Path, qt_app, fake_home: Path) -> None:
    _ = qt_app
    _ = fake_home
    harness = build_supervisor(tmp_path)
    try:
        working_events: list[int] = []
        automation_events: list[int] = []
        attention_events: list[int] = []
        harness.supervisor.workingChanged.connect(lambda: working_events.append(len(model_items(harness.supervisor.workingModel))))
        harness.supervisor.automationChanged.connect(lambda: automation_events.append(len(model_items(harness.supervisor.automationModel))))
        harness.supervisor.attentionChanged.connect(lambda: attention_events.append(len(model_items(harness.supervisor.attentionModel))))
        harness.supervisor.refresh()
        wait_until(lambda: harness.supervisor.overview.get("profileCount") == 2)
        harness.supervisor.selectProfile(harness.work_id)
        assert harness.supervisor.selectedProfile["id"] == harness.work_id
        assert model_items(harness.supervisor.workingModel) == []
        assert all(item["profileId"] == harness.work_id for item in model_items(harness.supervisor.automationModel))
        assert working_events and automation_events and attention_events
    finally:
        harness.runner.shutdown(grace_s=1.0)


def test_supervisor_does_not_project_hub_summary_as_attention(tmp_path: Path, qt_app, fake_home: Path) -> None:
    _ = qt_app
    _ = fake_home
    harness = build_supervisor(tmp_path)
    try:
        harness.chat_service.hubDetail = "✓ 中枢已启动 — 通道: telegram"
        harness.chat_service.lastError = ""
        harness.chat_service.hubDetailIsError = False
        harness.supervisor.refresh()
        wait_until(lambda: harness.supervisor.overview.get("profileCount") == 2)
        assert not any(
            str(item.get("id", "")).endswith(":hub:issue")
            for item in model_items(harness.supervisor.attentionModel)
        )
    finally:
        harness.runner.shutdown(grace_s=1.0)
