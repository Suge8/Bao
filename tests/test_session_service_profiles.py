from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest_plugins = ("tests._session_service_testkit",)

QtCore = pytest.importorskip("PySide6.QtCore")
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer


def _wait_briefly() -> None:
    loop = QEventLoop()
    QTimer.singleShot(300, loop.quit)
    loop.exec()


def test_bootstrap_storage_root_replaces_existing_session_manager(tmp_path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.session import SessionService
    from tests._session_service_testkit import _hub_local_ports

    runner = AsyncioRunner()
    runner.start()
    try:
        service = SessionService(runner)
        ready: list[object] = []
        service.hubLocalPortsReady.connect(ready.append)

        first_manager = MagicMock()
        first_manager.workspace = tmp_path / "state-a"
        second_manager = MagicMock()
        second_manager.workspace = tmp_path / "state-b"
        first = _hub_local_ports(first_manager)
        second = _hub_local_ports(second_manager)

        with patch("bao.hub.open_local_hub_ports", side_effect=[first, second]):
            service.bootstrapStorageRoot(str(first.state_root))
            _wait_briefly()
            service.bootstrapStorageRoot(str(second.state_root))
            _wait_briefly()

        assert service._local_hub_ports is second
        assert ready == [first, second]
    finally:
        runner.shutdown(grace_s=1.0)


def test_adopt_live_hub_runtime_marks_service_ready_without_rebinding_local_ports(tmp_path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.session import SessionService

    runner = AsyncioRunner()
    runner.start()
    try:
        service = SessionService(runner)
        service.adoptLiveHubRuntime(MagicMock(workspace=tmp_path / "state-live"))
        _wait_briefly()

        assert service._local_hub_ports is None
        assert service._hub_ready is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_adopt_live_hub_runtime_keeps_existing_local_ports(tmp_path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.session import SessionService
    from tests._session_service_testkit import _hub_local_ports

    runner = AsyncioRunner()
    runner.start()
    try:
        service = SessionService(runner)
        local_manager = MagicMock()
        local_manager.workspace = tmp_path / "state-live"
        local_ports = _hub_local_ports(local_manager)
        live_runtime = MagicMock(workspace=local_manager.workspace)

        service.initialize(local_ports)
        service.adoptLiveHubRuntime(live_runtime)
        _wait_briefly()

        assert service._local_hub_ports is local_ports
        assert service._hub_ready is True
    finally:
        runner.shutdown(grace_s=1.0)
