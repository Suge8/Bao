from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    channel: str
    chat_id: str
    status: str = "delivered"
    detail: str = ""

    @property
    def delivered(self) -> bool:
        return self.status == "delivered"

    @property
    def queued(self) -> bool:
        return self.status == "queued"

    @classmethod
    def delivered_result(cls, *, channel: str, chat_id: str, detail: str = "") -> "DeliveryResult":
        return cls(channel=channel, chat_id=chat_id, status="delivered", detail=detail)

    @classmethod
    def queued_result(cls, *, channel: str, chat_id: str, detail: str = "") -> "DeliveryResult":
        return cls(channel=channel, chat_id=chat_id, status="queued", detail=detail)
