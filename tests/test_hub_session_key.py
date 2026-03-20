from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def test_same_session_key_first_set_still_loads_history():
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.chat import ChatMessageModel
    from app.backend.hub import ChatService
    from tests._chat_service_testkit import _hub_local_ports

    runner = AsyncioRunner()
    runner.start()
    try:
        model = ChatMessageModel()
        svc = ChatService(model, runner)

        sm = MagicMock()
        sm.get_display_messages.return_value = [{"role": "user", "content": "hello"}]
        sm.get_session_list_entry.return_value = {
            "key": "desktop:local",
            "updated_at": "2026-03-19T03:00:00",
            "message_count": 1,
        }
        svc.setFallbackHubPorts(_hub_local_ports(sm))

        svc.setSessionKey("desktop:local")

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert model.rowCount() == 1
        assert sm.get_display_messages.call_count == 1
    finally:
        runner.shutdown(grace_s=1.0)
