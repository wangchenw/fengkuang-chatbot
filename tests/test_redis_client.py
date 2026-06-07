from redis.asyncio import Redis

from bot_service.integrations.redis_client import create_redis_client


def test_create_redis_client_uses_utf8_decoded_responses() -> None:
    client = create_redis_client("redis://localhost:6379/2")

    assert isinstance(client, Redis)
    assert client.connection_pool.connection_kwargs["encoding"] == "utf-8"
    assert client.connection_pool.connection_kwargs["decode_responses"] is True
