from __future__ import annotations


def test_session_get_history_filters_sourced_system_notifications() -> None:
    from bao.session.manager import Session

    s = Session("k")
    s.add_message("user", "hi")
    s.add_message("assistant", "ok")

    s.add_message("user", "gateway started", _source="desktop-system")
    s.add_message("system", "legacy system notice", _source="desktop-system")
    s.add_message("user", "[System: cron] scheduled", _source="cron")

    out = s.get_history()
    assert out == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "[System: cron] scheduled", "_source": "cron"},
    ]


def test_session_get_history_allows_explicit_system_events() -> None:
    from bao.session.manager import Session

    s = Session("k")
    s.add_message("user", "hi")
    s.add_message("user", '{"type":"system_event","name":"tool_failed"}', _source="system-event")
    s.add_message("assistant", "ack")

    out = s.get_history()
    assert out == [
        {"role": "user", "content": "hi"},
        {
            "role": "user",
            "content": '{"type":"system_event","name":"tool_failed"}',
            "_source": "system-event",
        },
        {"role": "assistant", "content": "ack"},
    ]
