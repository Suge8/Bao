from __future__ import annotations

from bao.hub._channel_binding import ChannelBindingStore
from bao.hub._route_index import SessionRouteIndex
from bao.hub._route_resolution import HubRouteResolver, SessionOrigin


def test_route_index_persists_session_profile_bindings(tmp_path) -> None:
    index_path = tmp_path / "hub-route-index.json"
    first = SessionRouteIndex(index_path)

    first.bind(" desktop:local::s1 ", " work ")

    second = SessionRouteIndex(index_path)
    assert second.resolve("desktop:local::s1") == "work"


def test_channel_binding_store_persists_origin_profile_bindings(tmp_path) -> None:
    binding_path = tmp_path / "hub-channel-bindings.json"
    first = ChannelBindingStore(binding_path)
    origin = SessionOrigin.create(
        channel=" Telegram ",
        chat_id=" -100123 ",
        metadata={"bot_id": " bot-1 ", "message_thread_id": " 42 "},
    )

    first.bind(origin.binding_key(), " work ")

    second = ChannelBindingStore(binding_path)
    assert origin.binding_key() == "channel=telegram|account=bot-1|peer=-100123|thread=42"
    assert second.resolve(origin.binding_key()) == "work"


def test_route_resolution_snapshot_includes_reason_and_origin_key(tmp_path) -> None:
    index = SessionRouteIndex(tmp_path / "hub-route-index.json")
    bindings = ChannelBindingStore(tmp_path / "hub-channel-bindings.json")
    origin = SessionOrigin.create(
        channel="telegram",
        chat_id="-100123",
        metadata={"bot_id": "bot-1", "message_thread_id": "42"},
    )
    bindings.bind(origin.binding_key(), "work")

    result = HubRouteResolver(
        route_index=index,
        channel_bindings=bindings,
        default_profile_id="default",
    ).resolve(
        explicit_profile_id="",
        session_key="",
        origin=origin,
    )

    assert result.reason == "origin_channel_binding"
    assert result.as_snapshot() == {
        "profile_id": "work",
        "source": "channel_binding",
        "session_key": "",
        "reason": "origin_channel_binding",
        "origin": {
            "channel": "telegram",
            "account_id": "bot-1",
            "peer_id": "-100123",
            "thread_id": "42",
        },
        "origin_key": "channel=telegram|account=bot-1|peer=-100123|thread=42",
    }
