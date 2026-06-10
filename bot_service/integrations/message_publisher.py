import logging
from typing import Protocol
from shared.message_contract import ChatMessage
from shared.redis_keys import messages_key
from bot_service.integrations.rabbitmq_publisher import RabbitMQPublisher


logger = logging.getLogger(__name__)

# Protocol ≈ Java 的 interface(但更松)
class MessagePublisher(Protocol):
    async def publish(self, match_id: str, message: ChatMessage) -> None: ...

    async def close(self) -> None: ...


class RedisMessagePublisher:
    """把弹幕写入redis stream，行为与 LiveTaskManager x.add一致"""
    def __init__(self, redis_client, stream_maxlen: int = 5000) -> None:
        self.redis = redis_client
        self.stream_maxlen = stream_maxlen

    async def publish(self, match_id: str, message: ChatMessage) -> None:
        await self.redis.xadd(
            messages_key(match_id),
            message.to_redis_fields(),
            maxlen=self.stream_maxlen,
            approximate=True,
        )

    async def close(self) -> None:
        "redis 连接统一由外部管理，这里不负责关闭"
        return None

class CompositePublisher:
    """组合多个 publisher，逐个转发；单个失败只记日志，不影响其他。"""

    def __init__(self, publishers: list[MessagePublisher]) -> None:
        self._publishers = publishers

    async def publish(self, match_id: str, message: ChatMessage) -> None:
        for publisher in self._publishers:
            try:
                await publisher.publish(match_id, message)
            except Exception:
                logger.exception(
                    "publisher %s 发布失败 match_id=%s",
                    type(publisher).__name__,
                    match_id,
                )

    async def close(self) -> None:
        for publisher in self._publishers:
            await publisher.close()


async def build_publisher(settings, redis_client) -> MessagePublisher:
    """根据 message_sink 配置组装出最终使用的 publisher。"""
    publishers: list[MessagePublisher] = []

    if settings.message_sink in ("redis", "both"):
        publishers.append(RedisMessagePublisher(redis_client))
        logger.info("Publisher registered: RedisMessagePublisher (message_sink=%s)", settings.message_sink)

    if settings.message_sink in ("rabbitmq", "both"):
        rabbitmq_publisher = RabbitMQPublisher(
            url=settings.rabbitmq_url,
            exchange_name=settings.rabbitmq_exchange,
            queue_name=settings.rabbitmq_queue,
            routing_key_template=settings.rabbitmq_routing_key_template,
            binding_key=settings.rabbitmq_binding_key,
            message_ttl_ms=settings.rabbitmq_message_ttl_ms,
        )
        await rabbitmq_publisher.connect()
        publishers.append(rabbitmq_publisher)
        logger.info("Publisher registered: RabbitMQPublisher (message_sink=%s)", settings.message_sink)

    logger.info(
        "CompositePublisher built with %d publisher(s): %s",
        len(publishers),
        [type(p).__name__ for p in publishers],
    )
    return CompositePublisher(publishers)