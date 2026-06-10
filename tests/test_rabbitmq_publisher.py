import json

from bot_service.integrations.rabbitmq_publisher import RabbitMQPublisher
from shared.message_contract import ChatMessage


class FakeExchange:
    def __init__(self) -> None:
        self.message = None
        self.routing_key = None

    async def publish(self, message, routing_key: str) -> None:
        self.message = message
        self.routing_key = routing_key


async def test_rabbitmq_publish_uses_message_id_in_amqp_properties() -> None:
    publisher = RabbitMQPublisher(
        url="amqp://guest:guest@localhost/",
        exchange_name="livestream.danmaku",
        queue_name="livestream.danmaku.queue",
        routing_key_template="match.{match_id}",
        binding_key="match.#",
        message_ttl_ms=3600000,
        use_default_exchange=False,
    )
    exchange = FakeExchange()
    publisher._exchange = exchange

    message = ChatMessage(
        message_id="msg_test_001",
        match_id="match_001",
        bot_id="bot_001",
        bot_name="热血球迷",
        content="这球看得我心跳加速",
        match_time="第68分钟",
        event="live",
        ts=1717660800,
    )

    await publisher.publish("match_001", message)

    assert exchange.routing_key == "match.match_001"
    assert json.loads(exchange.message.body)["message_id"] == "msg_test_001"
    assert exchange.message.message_id == "msg_test_001"
    assert exchange.message.correlation_id == "msg_test_001"
