"""QQ channel implementation using botpy SDK."""

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Any

from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
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
        self._bot_task: asyncio.Task[None] | None = None

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

        self._running = True
        bot_class = _make_bot_class(self)
        self._client = bot_class()

        self._bot_task = asyncio.create_task(self._run_bot())
        logger.info("📡 已启动 / bot started: C2C private message")
        try:
            await self._bot_task
        except asyncio.CancelledError:
            pass

    async def _run_bot(self) -> None:
        """Run the bot connection with auto-reconnect."""
        secret = self.config.secret.get_secret_value()
        while self._running:
            try:
                await self._client.start(appid=self.config.app_id, secret=secret)
            except Exception as e:
                logger.warning("⚠️ 连接异常 / bot error: {}", e)
            if self._running:
                logger.info("🔄 准备重连 / reconnecting: wait=5s")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the QQ bot."""
        self._running = False
        self.mark_not_ready()
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
        logger.info("✅ 已停止 / bot stopped: QQ")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through QQ."""
        if not self._client:
            logger.warning("⚠️ 未初始化 / client not initialized: QQ")
            return
        try:
            msg_id = msg.metadata.get("message_id") if isinstance(msg.metadata, dict) else None
            await self._client.api.post_c2c_message(
                openid=msg.chat_id,
                msg_type=0,
                content=msg.content,
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
