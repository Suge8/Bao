"""QQ channel implementation using botpy SDK."""

from collections import deque
from typing import TYPE_CHECKING, Any

from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import ProgressBuffer
from bao.config.schema import QQConfig

_qq_available = False
try:
    from botpy.message import C2CMessage

    _qq_available = True
except ImportError:
    pass

QQ_AVAILABLE = _qq_available

if TYPE_CHECKING:
    from botpy.message import C2CMessage


def _make_bot_class(channel: "QQChannel") -> type[Any]:
    """Create a botpy Client subclass bound to the given channel."""

    import botpy as _botpy

    intents = _botpy.Intents(public_messages=True, direct_message=True)

    class _Bot(_botpy.Client):
        def __init__(self):
            super().__init__(intents=intents, ext_handlers=False)

        async def on_ready(self):
            logger.info("✅ 已就绪 / bot ready: {}", getattr(self.robot, "name", ""))
            channel.mark_ready()

        async def on_c2c_message_create(self, message: Any):
            await channel._on_message(message)

        async def on_direct_message_create(self, message):
            await channel._on_message(message)

    return _Bot


class QQChannel(BaseChannel):
    """QQ channel using botpy SDK with WebSocket connection."""

    name = "qq"

    def __init__(self, config: QQConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: QQConfig = config
        self._client: Any = None
        self._processed_ids: deque[str] = deque(maxlen=1000)
        self._progress_msg_id: dict[str, str | None] = {}
        self._progress_handler = ProgressBuffer(self._send_text)

    async def start(self) -> None:
        """Start the QQ bot."""
        self.mark_not_ready()
        if not QQ_AVAILABLE:
            logger.error("❌ 未安装 / sdk missing: pip install qq-botpy")
            self.mark_ready()
            return

        secret = self.config.secret.get_secret_value()
        if not self.config.app_id or not secret:
            logger.error("❌ 未配置 / not configured: QQ app_id/secret")
            self.mark_ready()
            return

        self._start_lifecycle()
        bot_class = _make_bot_class(self)
        self._client = bot_class()
        logger.info("📡 已启动 / bot started: C2C private message")

        secret = self.config.secret.get_secret_value()
        await self._run_reconnect_loop(
            lambda: self._client.start(appid=self.config.app_id, secret=secret),
            label="QQ bot",
        )

    async def stop(self) -> None:
        """Stop the QQ bot."""
        self._clear_progress()
        self._progress_msg_id.clear()
        self._stop_lifecycle()
        self.mark_not_ready()
        self._reset_lifecycle()
        logger.info("✅ 已停止 / bot stopped: QQ")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through QQ."""
        if not self._client:
            logger.warning("⚠️ 未初始化 / client not initialized: QQ")
            return
        meta = msg.metadata if isinstance(msg.metadata, dict) else {}
        raw_msg_id = meta.get("message_id")
        self._progress_msg_id[msg.chat_id] = raw_msg_id if isinstance(raw_msg_id, str) else None
        await self._dispatch_progress_text(msg, flush_progress=False)
        if bool(meta.get("_progress_clear")) or not bool(meta.get("_progress")):
            self._progress_msg_id.pop(msg.chat_id, None)

    async def _send_text(self, chat_id: str, text: str) -> None:
        if not self._client or not text:
            return
        try:
            msg_id = self._progress_msg_id.get(chat_id)
            await self._client.api.post_c2c_message(
                openid=chat_id,
                msg_type=0,
                content=text,
                msg_id=msg_id,
            )
        except Exception as e:
            logger.error("❌ 发送失败 / send failed: {}", e)

    async def _on_message(self, data: "C2CMessage") -> None:
        """Handle incoming message from QQ."""
        try:
            # Dedup by message ID
            if data.id in self._processed_ids:
                return
            self._processed_ids.append(data.id)

            author = data.author
            user_id = str(getattr(author, "id", None) or getattr(author, "user_openid", "unknown"))
            content = (data.content or "").strip()
            if not content:
                return

            await self._handle_message(
                sender_id=user_id,
                chat_id=user_id,
                content=content,
                metadata={"message_id": data.id},
            )
        except Exception as e:
            logger.error("❌ 处理失败 / message error: {}", e)
