from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.chat import ChatMessageModel
from app.backend.gateway import ChatService


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def test_same_session_key_first_set_still_loads_history():
    runner = AsyncioRunner()
    runner.start()
    try:
        model = ChatMessageModel()
        svc = ChatService(model, runner)

        mock_session = MagicMock()
        mock_session.get_history.return_value = [{"role": "user", "content": "hello"}]
        sm = MagicMock()
        sm.get_or_create.return_value = mock_session
        svc.setSessionManager(sm)

        svc.setSessionKey("desktop:local")

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert model.rowCount() == 1
        assert sm.get_or_create.call_count == 1
    finally:
        runner.shutdown(grace_s=1.0)
