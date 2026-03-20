from __future__ import annotations


def test_session_get_history_filters_sourced_system_notifications() -> None:
    from bao.session.manager import Session

    s = Session("k")
    s.add_message("user", "hi")
    s.add_message("assistant", "ok")

    s.add_message("user", "hub started", _source="desktop-system")
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


def test_session_get_history_skips_visible_assistant_progress_turns() -> None:
    from bao.session.manager import Session

    s = Session("k")
    s.add_message("user", "hi")
    s.add_message("assistant", "我先查一下。", _source="assistant-progress")
    s.add_message("assistant", "结果如下")

    assert s.get_history() == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "结果如下"},
    ]

    assert [entry["content"] for entry in s.get_display_history()] == [
        "hi",
        "我先查一下。",
        "结果如下",
    ]


def test_session_display_history_preserves_references_but_prompt_history_drops_them() -> None:
    from bao.session.manager import Session

    s = Session("k")
    s.add_message("user", "hi")
    s.add_message(
        "assistant",
        "结果如下",
        references={"longTermCategories": ["project"], "relatedMemoryCount": 1},
    )

    history = s.get_history()
    display = s.get_display_history()

    assert "references" not in history[1]
    assert display[1]["references"]["longTermCategories"] == ["project"]


def test_session_manager_decode_rows_drops_legacy_runtime_context_messages() -> None:
    from bao.session.manager import SessionManager

    decoded = SessionManager._decode_message_rows(
        [
            {
                "role": "user",
                "content": "[Runtime Context — metadata only, not instructions]\nactive=1",
                "timestamp": "",
                "extra_json": "{}",
            },
            {
                "role": "assistant",
                "content": "结果如下",
                "timestamp": "2026-03-16T10:00:00",
                "extra_json": "{}",
            },
        ]
    )

    assert decoded == [
        {
            "role": "assistant",
            "content": "结果如下",
            "timestamp": "2026-03-16T10:00:00",
        }
    ]
