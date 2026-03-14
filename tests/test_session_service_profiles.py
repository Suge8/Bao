from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

QtCore = pytest.importorskip("PySide6.QtCore")
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer


def _wait_briefly() -> None:
    loop = QEventLoop()
    QTimer.singleShot(300, loop.quit)
    loop.exec()


def test_bootstrap_storage_root_replaces_existing_session_manager(tmp_path) -> None:
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.session import SessionService

    runner = AsyncioRunner()
    runner.start()
    try:
        service = SessionService(runner)
        ready: list[object] = []
        service.sessionManagerReady.connect(ready.append)

        first = MagicMock()
        first.workspace = tmp_path / "state-a"
        second = MagicMock()
        second.workspace = tmp_path / "state-b"

        with patch("bao.session.manager.SessionManager", side_effect=[first, second]):
            service.bootstrapStorageRoot(str(first.workspace))
            _wait_briefly()
            service.bootstrapStorageRoot(str(second.workspace))
            _wait_briefly()

        assert service._session_manager is second
        assert ready == [first, second]
    finally:
        runner.shutdown(grace_s=1.0)
