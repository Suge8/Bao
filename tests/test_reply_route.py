from __future__ import annotations

import pytest

from bao.agent.reply_route import ReplyRoute, TurnContextStore, normalize_reply_metadata
from bao.agent.reply_route_models import ReplyRouteInput

pytestmark = pytest.mark.unit


def test_normalize_reply_metadata_keeps_valid_slack_thread_only() -> None:
    metadata = normalize_reply_metadata(
        {
            "slack": {
                "thread_ts": " 1712345678.900 ",
                "channel_type": "  im ",
                "ignored": "value",
            },
            "other": {"x": 1},
        }
    )

    assert metadata == {
        "slack": {
            "thread_ts": "1712345678.900",
            "channel_type": "im",
        }
    }


def test_reply_route_create_uses_session_key_fallback_and_normalizes_message_id() -> None:
    route = ReplyRoute.create(
        ReplyRouteInput(
            channel=" Desktop ",
            chat_id=" local ",
            lang=" ZH ",
            message_id=42,
        )
    )

    assert route.channel == "desktop"
    assert route.chat_id == "local"
    assert route.session_key == "desktop:local"
    assert route.lang == "zh"
    assert route.message_id == "42"


def test_reply_route_create_prefers_explicit_session_key_and_filters_invalid_metadata() -> None:
    route = ReplyRoute.create(
        ReplyRouteInput(
            channel="slack",
            chat_id="channel",
            session_key=" session-1 ",
            message_id=True,
            reply_metadata={"slack": {"thread_ts": ""}},
        )
    )

    assert route.session_key == "session-1"
    assert route.message_id is None
    assert route.reply_metadata == {}


def test_turn_context_store_uses_default_route_and_can_replace_it() -> None:
    store = TurnContextStore(
        "reply_route_test",
        ReplyRouteInput(channel="Slack", chat_id="room", lang="EN"),
    )

    default_route = store.get()
    assert default_route.channel == "slack"
    assert default_route.session_key == "slack:room"
    assert default_route.lang == "en"

    store.set(
        ReplyRouteInput(
            channel="discord",
            chat_id="thread",
            session_key="discord:thread:child",
            reply_metadata={"slack": {"thread_ts": "123.456"}},
        )
    )

    updated_route = store.get()
    assert updated_route.channel == "discord"
    assert updated_route.session_key == "discord:thread:child"
    assert updated_route.reply_metadata == {"slack": {"thread_ts": "123.456"}}
