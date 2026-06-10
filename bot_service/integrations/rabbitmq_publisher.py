import asyncio
import logging

import aio_pika
import aiormq.exceptions

from shared.message_contract import ChatMessage

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """把弹幕发布到 RabbitMQ。支持 topic exchange 或默认 exchange 直投队列。"""

    def __init__(
        self,
        url: str,
        exchange_name: str,
        queue_name: str,
        routing_key_template: str,
        binding_key: str,
        message_ttl_ms: int,
        use_default_exchange: bool = False,
    ) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._queue_name = queue_name
        self._routing_key_template = routing_key_template
        self._binding_key = binding_key
        self._message_ttl_ms = message_ttl_ms
        self._use_default_exchange = use_default_exchange
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._topology_lock = asyncio.Lock()

    def _exchange_label(self) -> str:
        return "(default)" if self._use_default_exchange else self._exchange_name

    async def _setup_topology(self) -> None:
        if self._connection is None:
            raise RuntimeError("RabbitMQPublisher 未连接，请先调用 connect()")

        async with self._topology_lock:
            # publisher_confirms=True 开启发布确认，保证 broker 真正收到
            self._channel = await self._connection.channel(publisher_confirms=True)
            queue = await self._channel.declare_queue(
                self._queue_name,
                durable=True,
                arguments={"x-message-ttl": self._message_ttl_ms},
            )

            if self._use_default_exchange:
                self._exchange = self._channel.default_exchange
                return

            # topic 模式：声明 exchange + 绑定到 queue
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            await queue.bind(self._exchange, routing_key=self._binding_key)

    async def _on_reconnect(self, _connection: aio_pika.abc.AbstractConnection) -> None:
        logger.warning("RabbitMQ reconnected, re-declaring topology")
        await self._setup_topology()

    async def connect(self) -> None:
        logger.info(
            "RabbitMQ connecting url=%s mode=%s exchange=%s queue=%s binding=%s ttl_ms=%s",
            self._url,
            "default" if self._use_default_exchange else "topic",
            self._exchange_label(),
            self._queue_name,
            self._binding_key if not self._use_default_exchange else "N/A",
            self._message_ttl_ms,
        )
        # connect_robust 自带断线自动重连；重连后 channel 会失效，需重新声明拓扑
        self._connection = await aio_pika.connect_robust(self._url)
        self._connection.reconnect_callbacks.add(self._on_reconnect)
        await self._setup_topology()

        if self._use_default_exchange:
            logger.info(
                "RabbitMQ connected OK mode=default queue=%s routing_key=%s",
                self._queue_name,
                self._queue_name,
            )
            return

        logger.info(
            "RabbitMQ connected OK mode=topic exchange=%s queue=%s binding=%s",
            self._exchange_name,
            self._queue_name,
            self._binding_key,
        )

    async def _publish_bytes(self, body: bytes, routing_key: str, message_id: str) -> None:
        if self._exchange is None:
            raise RuntimeError("RabbitMQPublisher 未连接，请先调用 connect()")

        await self._exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message_id,
                correlation_id=message_id,
            ),
            routing_key=routing_key,
        )

    @staticmethod
    def _should_redeclare_topology(exc: BaseException) -> bool:
        return isinstance(
            exc,
            (
                aiormq.exceptions.ChannelNotFoundEntity,
                aiormq.exceptions.ChannelInvalidStateError,
                aiormq.exceptions.ChannelClosed,
            ),
        )

    async def publish(self, match_id: str, message: ChatMessage) -> None:
        if self._exchange is None:
            raise RuntimeError("RabbitMQPublisher 未连接，请先调用 connect()")

        if self._use_default_exchange:
            routing_key = self._queue_name
        else:
            routing_key = self._routing_key_template.format(match_id=match_id)

        body = message.to_json_bytes()
        logger.info(
            "RabbitMQ publish start exchange=%s queue=%s routing_key=%s "
            "message_id=%s match_id=%s bot_id=%s bot_name=%s content=%s",
            self._exchange_label(),
            self._queue_name,
            routing_key,
            message.message_id,
            message.match_id,
            message.bot_id,
            message.bot_name,
            message.content[:80],
        )
        try:
            await self._publish_bytes(body, routing_key, message.message_id)
        except Exception as exc:
            if not self._should_redeclare_topology(exc):
                raise
            logger.warning(
                "RabbitMQ publish failed (%s), re-declaring topology and retrying once",
                exc,
            )
            await self._setup_topology()
            await self._publish_bytes(body, routing_key, message.message_id)

        logger.info(
            "RabbitMQ publish OK exchange=%s routing_key=%s body_size=%s",
            self._exchange_label(),
            routing_key,
            len(body),
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
