"""Message bus module for decoupled channel-agent communication."""

from bao.bus.events import InboundMessage, OutboundMessage
from bao.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
