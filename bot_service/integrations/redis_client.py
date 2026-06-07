from redis.asyncio import Redis

from bot_service.config.settings import settings
from bot_service.integrations.agno_agent import create_mimo_agent


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


redis_client = create_redis_client(settings.redis_url)
mimo_agent = create_mimo_agent(
    api_key=settings.mimo_api_key,
    base_url=settings.mimo_base_url,
    model=settings.mimo_model,
)
