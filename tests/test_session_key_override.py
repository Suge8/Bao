
from datetime import datetime
from bao.bus.events import InboundMessage


def _msg(channel="slack", chat_id="C123", metadata=None):
    return InboundMessage(
        channel=channel,
        sender_id="U999",
        chat_id=chat_id,
        content="hello",
        timestamp=datetime.now(),
        metadata=metadata or {},
    )


def test_default_session_key() -> None:
    msg = _msg(channel="telegram", chat_id="8281248569")
    assert msg.session_key == "telegram:8281248569"


def test_session_key_override_from_metadata() -> None:
    msg = _msg(metadata={"session_key": "slack:C123:1700000000.000100"})
    assert msg.session_key == "slack:C123:1700000000.000100"


def test_session_key_override_ignored_if_empty() -> None:
    msg = _msg(channel="slack", chat_id="C123", metadata={"session_key": ""})
    assert msg.session_key == "slack:C123"


def test_session_key_override_ignored_if_not_string() -> None:
    msg = _msg(channel="slack", chat_id="C123", metadata={"session_key": 12345})
    assert msg.session_key == "slack:C123"


def test_slack_thread_session_key_format() -> None:
    """Verify thread_ts produces the expected key format."""
    thread_ts = "1700000000.000100"
    chat_id = "C456"
    expected = f"slack:{chat_id}:{thread_ts}"
    msg = _msg(channel="slack", chat_id=chat_id, metadata={"session_key": expected})
    assert msg.session_key == expected
    assert thread_ts in msg.session_key
