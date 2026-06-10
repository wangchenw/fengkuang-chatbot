import logging

import aio_pika

from shared.message_contract import ChatMessage

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """把弹幕发布到我方自有的 RabbitMQ 拓扑(topic exchange + 共享 queue)。"""

    def __init__(
        self,
        url: str,
        exchange_name: str,
        queue_name: str,
        routing_key_template: str,
        binding_key: str,
        message_ttl_ms: int,
    ) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._queue_name = queue_name
        self._routing_key_template = routing_key_template
        self._binding_key = binding_key
        self._message_ttl_ms = message_ttl_ms
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        logger.info(
            "RabbitMQ connecting url=%s exchange=%s queue=%s binding=%s ttl_ms=%s",
            self._url,
            self._exchange_name,
            self._queue_name,
            self._binding_key,
            self._message_ttl_ms,
        )
        # connect_robust 自带断线自动重连
        self._connection = await aio_pika.connect_robust(self._url)
        # publisher_confirms=True 开启发布确认，保证 broker 真正收到
        self._channel = await self._connection.channel(publisher_confirms=True)

        # 我方拥有拓扑：声明 exchange + queue + 绑定，全部 durable
        self._exchange = await self._channel.declare_exchange(
            self._exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        queue = await self._channel.declare_queue(
            self._queue_name,
            durable=True,
            arguments={"x-message-ttl": self._message_ttl_ms},
        )
        await queue.bind(self._exchange, routing_key=self._binding_key)
        logger.info(
            "RabbitMQ connected OK exchange=%s queue=%s binding=%s",
            self._exchange_name,
            self._queue_name,
            self._binding_key,
        )

    async def publish(self, match_id: str, message: ChatMessage) -> None:
        if self._exchange is None:
            raise RuntimeError("RabbitMQPublisher 未连接，请先调用 connect()")

        routing_key = self._routing_key_template.format(match_id=match_id)
        body = message.to_json_bytes()
        logger.info(
            "RabbitMQ publish start exchange=%s queue=%s routing_key=%s "
            "match_id=%s bot_id=%s bot_name=%s content=%s",
            self._exchange_name,
            self._queue_name,
            routing_key,
            message.match_id,
            message.bot_id,
            message.bot_name,
            message.content[:80],
        )
        await self._exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )
        logger.info(
            "RabbitMQ publish OK exchange=%s routing_key=%s body_size=%s",
            self._exchange_name,
            routing_key,
            len(body),
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()