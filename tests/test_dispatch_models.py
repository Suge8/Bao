from __future__ import annotations

import pytest

from bao.agent.dispatch_models import RouteKey, WakeRequest

pytestmark = pytest.mark.unit


def test_route_key_create_reuses_reply_route_normalization() -> None:
    route = RouteKey.create(
        profile_id=" work ",
        channel=" Desktop ",
        chat_id=" local ",
        reply_target_id=42,
    )

    assert route.profile_id == "work"
    assert route.channel == "desktop"
    assert route.chat_id == "local"
    assert route.session_key == "desktop:local"
    assert route.reply_target_id == "42"


def test_wake_request_to_inbound_message_preserves_metadata_and_ephemeral_flag() -> None:
    wake = WakeRequest.create(
        content="hello",
        route=RouteKey.create(profile_id="work", session_key="desktop:local::s1", channel="desktop", chat_id="local"),
        media=["/tmp/image.png"],
        metadata={"source": "cron"},
        ephemeral=True,
    )

    msg = wake.to_inbound_message()

    assert dict(wake.metadata) == {"source": "cron"}
    assert msg.channel == "desktop"
    assert msg.chat_id == "local"
    assert msg.media == ["/tmp/image.png"]
    assert msg.metadata == {"source": "cron", "_ephemeral": True}
