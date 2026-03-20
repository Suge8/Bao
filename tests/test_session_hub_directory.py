from __future__ import annotations

from pathlib import Path

from bao.hub._directory_models import TranscriptReadRequest, decode_transcript_cursor
from bao.hub._route_resolution import SessionOrigin
from bao.hub._session_directory_identity import build_binding_key, build_session_ref
from bao.hub._session_directory_models import (
    IdentityLinkRecord,
    SessionBindingRecord,
    SessionPreferenceRecord,
    SessionRecord,
)
from bao.hub._session_directory_updater import get_session_directory_runtime
from bao.hub.directory import HubDirectory
from bao.session.manager import SessionManager


def _build_session(manager: SessionManager, key: str, messages: list[tuple[str, str]]) -> None:
    session = manager.get_or_create(key)
    for role, content in messages:
        session.add_message(role, content)
    manager.save(session)


def test_hub_directory_lists_active_key_and_children(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    parent_key = "desktop:local::parent"
    child_key = "desktop:local::child"
    _build_session(manager, parent_key, [("user", "hello")])
    child = manager.get_or_create(child_key)
    child.metadata["parent_session_key"] = parent_key
    child.add_message("assistant", "child")
    manager.save(child)
    manager.set_active_session_key("desktop:local", child_key)

    directory = HubDirectory(manager)

    sessions, active_key = directory.list_sessions_with_active_key("desktop:local")

    assert active_key == child_key
    assert {item["key"] for item in sessions} == {parent_key, child_key}
    assert [item["key"] for item in directory.list_children(parent_key)] == [child_key]


def test_hub_directory_read_transcript_supports_tail_range_full_and_ref(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    key = "desktop:local::cursor"
    _build_session(
        manager,
        key,
        [
            ("user", "one"),
            ("assistant", "two"),
            ("user", "three"),
            ("assistant", "four"),
        ],
    )
    directory = HubDirectory(manager)

    tail = directory.read_transcript(key, TranscriptReadRequest(mode="tail", limit=2))
    assert [message["content"] for message in tail.messages] == ["three", "four"]
    assert tail.has_more_before is True
    assert decode_transcript_cursor(tail.previous_cursor) == 0

    page = directory.read_transcript(
        key,
        TranscriptReadRequest(
            mode="range",
            limit=2,
            cursor=tail.previous_cursor,
            transcript_ref=tail.transcript_ref,
        ),
    )
    assert [message["content"] for message in page.messages] == ["one", "two"]
    assert page.has_more_after is True
    assert decode_transcript_cursor(page.next_cursor) == 2

    full = directory.read_transcript(
        key,
        TranscriptReadRequest(mode="full", transcript_ref=tail.transcript_ref),
    )
    assert [message["content"] for message in full.messages] == ["one", "two", "three", "four"]


def test_hub_directory_rejects_stale_transcript_ref(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    key = "desktop:local::ref"
    _build_session(manager, key, [("assistant", "first")])
    directory = HubDirectory(manager)
    first = directory.read_transcript(key, TranscriptReadRequest(mode="tail", limit=1))

    _build_session(manager, key, [("assistant", "second")])

    try:
        directory.read_transcript(
            key,
            TranscriptReadRequest(mode="full", transcript_ref=first.transcript_ref),
        )
    except ValueError as exc:
        assert str(exc) == "transcript_ref_mismatch"
    else:
        raise AssertionError("expected transcript_ref_mismatch")


def test_session_directory_models_share_binding_key_contract() -> None:
    record = SessionRecord.create(
        session_key="telegram:-100123::main",
        channel=" Telegram ",
        account_id=" bot-1 ",
        peer_id=" -100123 ",
        thread_id=" 42 ",
        title=" Bao Dev ",
        participants_preview=[" Alice ", "", "Bob"],
    )

    assert record.session_ref == build_session_ref(
        session_key="telegram:-100123::main",
        channel="telegram",
        account_id="bot-1",
        peer_id="-100123",
        thread_id="42",
    )
    assert record.binding_key() == "channel=telegram|account=bot-1|peer=-100123|thread=42"
    assert record.participants_preview == ("Alice", "Bob")

    binding = SessionBindingRecord.create(
        session_ref=record.session_ref,
        channel="telegram",
        account_id="bot-1",
        peer_id="-100123",
        thread_id="42",
        source=" explicit ",
    )
    assert binding.binding_key == record.binding_key()
    assert binding.source == "explicit"
    assert build_binding_key(channel="telegram", account_id="bot-1", peer_id="-100123", thread_id="42") == record.binding_key()


def test_session_ref_falls_back_to_session_key_when_route_is_unknown() -> None:
    first = build_session_ref(session_key="desktop:local::main", channel="", peer_id="")
    second = build_session_ref(session_key=" desktop:local::main ", channel=None, peer_id=None)

    assert first
    assert first == second


def test_session_directory_preference_and_identity_models_normalize_inputs() -> None:
    preference = SessionPreferenceRecord.create(
        scope=" profile:work ",
        channel=" Telegram ",
        default_session_ref=" sess_abc ",
        reason=" recent_success ",
    )
    identity = IdentityLinkRecord.create(
        identity_ref=" ident_alice ",
        confidence=" candidate ",
        members=[
            {"channel": " imessage ", "peer_id": " +61 400 ", "session_ref": " sess_ios "},
            {"channel": "telegram", "peer_id": " alice_foo "},
            {"channel": "", "peer_id": "ignored"},
        ],
    )

    assert preference.as_snapshot() == {
        "scope": "profile:work",
        "channel": "telegram",
        "default_session_ref": "sess_abc",
        "reason": "recent_success",
        "updated_at": "",
    }
    assert identity.confidence == "candidate"
    assert [member.as_snapshot() for member in identity.members] == [
        {
            "channel": "imessage",
            "peer_id": "+61 400",
            "account_id": "",
            "thread_id": "",
            "session_ref": "sess_ios",
        },
        {
            "channel": "telegram",
            "peer_id": "alice_foo",
            "account_id": "",
            "thread_id": "",
            "session_ref": "",
        },
    ]


def test_session_directory_first_observed_materializes_record_and_binding(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    session_key = "telegram:-100123:topic:42::thread"
    origin = SessionOrigin.create(
        channel="telegram",
        chat_id="-100123",
        metadata={"bot_id": "bot-1", "message_thread_id": 42},
    )

    directory.observe_origin(session_key, origin)

    record = get_session_directory_runtime(manager).store.get_record(session_key)
    assert record is not None
    assert record.channel == "telegram"
    assert record.peer_id == "-100123"
    assert record.thread_id == "42"
    assert record.account_id == "bot-1"
    assert record.availability == "active"
    binding = get_session_directory_runtime(manager).store.get_binding(record.binding_key())
    assert binding is not None
    assert binding.session_ref == record.session_ref
    assert binding.source == "observed"


def test_session_directory_change_listener_does_not_materialize_empty_session(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    HubDirectory(manager)
    manager.save(manager.get_or_create("desktop:local::draft"))

    assert get_session_directory_runtime(manager).store.get_record("desktop:local::draft") is None


def test_session_directory_deleted_change_marks_deleted_without_implicit_runtime_delete(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    session_key = "desktop:local::main"
    origin = SessionOrigin.create(channel="desktop", chat_id="local")
    directory.observe_origin(session_key, origin)

    manager.set_session_running(session_key, False)
    record = get_session_directory_runtime(manager).store.get_record(session_key)
    assert record is not None
    assert record.availability != "deleted"

    assert manager.delete_session(session_key) is True
    deleted = get_session_directory_runtime(manager).store.get_record(session_key)
    assert deleted is not None
    assert deleted.availability == "deleted"


def test_hub_directory_recent_lookup_default_and_resolve_use_local_read_plane(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    telegram_key = "telegram:-100123:topic:42::thread"
    desktop_key = "desktop:local::main"
    desktop_origin = SessionOrigin.create(channel="desktop", chat_id="local")
    telegram_origin = SessionOrigin.create(
        channel="telegram",
        chat_id="-100123",
        metadata={"bot_id": "bot-1", "message_thread_id": 42},
    )

    _build_session(manager, desktop_key, [("user", "desk")])
    _build_session(manager, telegram_key, [("assistant", "tg")])
    directory.observe_origin(desktop_key, desktop_origin)
    directory.observe_origin(telegram_key, telegram_origin)

    recent = directory.list_recent_sessions(limit=2)
    assert {item["session_key"] for item in recent} == {desktop_key, telegram_key}

    lookup = directory.lookup_sessions(query="-100123", limit=2, channel="telegram")
    assert [item["session_key"] for item in lookup] == [telegram_key]
    assert lookup[0]["binding_key"] == "channel=telegram|account=bot-1|peer=-100123|thread=42"

    default_session = directory.get_default_session(channel="desktop", session_key=desktop_key)
    assert default_session["session_key"] == desktop_key
    assert default_session["default"] is True
    assert default_session["reason"] == "current_session"

    resolved = directory.resolve_session_ref(session_ref=lookup[0]["session_ref"])
    assert resolved["session_key"] == telegram_key


def test_hub_directory_default_skips_deleted_records(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    active_key = "desktop:local::active"
    deleted_key = "desktop:local::deleted"
    origin = SessionOrigin.create(channel="desktop", chat_id="local")

    _build_session(manager, active_key, [("assistant", "active")])
    _build_session(manager, deleted_key, [("assistant", "old")])
    directory.observe_origin(active_key, origin)
    directory.observe_origin(deleted_key, origin)
    assert manager.delete_session(deleted_key) is True

    default_session = directory.get_default_session(channel="desktop")

    assert default_session["session_key"] == active_key


def test_hub_directory_default_preference_overrides_recent_fallback(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    first_key = "desktop:local::alpha"
    second_key = "desktop:local::beta"
    origin = SessionOrigin.create(channel="desktop", chat_id="local")

    _build_session(manager, first_key, [("assistant", "alpha")])
    _build_session(manager, second_key, [("assistant", "beta")])
    directory.observe_origin(first_key, origin)
    directory.observe_origin(second_key, origin)
    first_record = get_session_directory_runtime(manager).store.get_record(first_key)
    second_record = get_session_directory_runtime(manager).store.get_record(second_key)
    assert first_record is not None
    assert second_record is not None

    preference = get_session_directory_runtime(manager).bindings.set_default_session_preference(
        scope="profile:work",
        channel="desktop",
        default_session_ref=first_record.session_ref,
        reason="binding",
    )
    assert preference["default_session_ref"] == first_record.session_ref

    default_session = directory.get_default_session(channel="desktop", scope="profile:work")
    assert default_session["session_key"] == first_key
    assert default_session["reason"] == "binding"
    assert default_session["scope"] == "profile:work"


def test_hub_directory_lookup_projects_cross_channel_identity_candidates(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    imessage_key = "imessage:+61400::focus"
    telegram_key = "telegram:alice_foo::main"
    imessage_origin = SessionOrigin.create(channel="imessage", chat_id="+61400")
    telegram_origin = SessionOrigin.create(channel="telegram", chat_id="alice_foo")

    _build_session(manager, imessage_key, [("assistant", "ios")])
    _build_session(manager, telegram_key, [("assistant", "tg")])
    directory.observe_origin(imessage_key, imessage_origin)
    directory.observe_origin(telegram_key, telegram_origin)

    imessage_record = get_session_directory_runtime(manager).store.get_record(imessage_key)
    telegram_record = get_session_directory_runtime(manager).store.get_record(telegram_key)
    assert imessage_record is not None
    assert telegram_record is not None

    identity = get_session_directory_runtime(manager).bindings.upsert_identity_link(
        identity_ref="ident_alice",
        confidence="explicit",
        members=[
            {
                "channel": "imessage",
                "peer_id": "+61400",
                "session_ref": imessage_record.session_ref,
            },
            {
                "channel": "telegram",
                "peer_id": "alice_foo",
                "session_ref": telegram_record.session_ref,
            },
        ],
    )
    assert identity["identity_ref"] == "ident_alice"

    results = directory.lookup_sessions(query="ident_alice", limit=5)
    assert {item["session_key"] for item in results} == {imessage_key, telegram_key}
    assert {item["identity_ref"] for item in results} == {"ident_alice"}

    resolved = directory.resolve_session_ref(session_ref=telegram_record.session_ref)
    assert resolved["identity_ref"] == "ident_alice"


def test_hub_directory_resolve_delivery_target_restores_telegram_topic_metadata(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    session_key = "telegram:-100123:topic:42::thread"
    _build_session(manager, session_key, [("assistant", "hello")])
    directory.observe_origin(
        session_key,
        SessionOrigin.create(
            channel="telegram",
            chat_id="-100123",
            metadata={"bot_id": "bot-1", "message_thread_id": 42},
        ),
    )
    record = get_session_directory_runtime(manager).store.get_record(session_key)
    assert record is not None

    target = directory.resolve_delivery_target(session_ref=record.session_ref)

    assert target == {
        "session_ref": record.session_ref,
        "session_key": session_key,
        "channel": "telegram",
        "chat_id": "-100123",
        "metadata": {"message_thread_id": "42"},
    }


def test_hub_directory_resolve_delivery_target_restores_slack_thread_metadata(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    session_key = "slack:C123:1710000.123::thread"
    _build_session(manager, session_key, [("assistant", "hello")])
    directory.observe_origin(
        session_key,
        SessionOrigin.create(
            channel="slack",
            chat_id="C123",
            metadata={"thread_ts": "1710000.123"},
        ),
    )
    record = get_session_directory_runtime(manager).store.get_record(session_key)
    assert record is not None

    target = directory.resolve_delivery_target(session_ref=record.session_ref)

    assert target == {
        "session_ref": record.session_ref,
        "session_key": session_key,
        "channel": "slack",
        "chat_id": "C123",
        "metadata": {"slack": {"thread_ts": "1710000.123", "channel_type": "channel"}},
    }
