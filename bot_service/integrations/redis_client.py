from redis.asyncio import Redis

from bot_service.config.settings import settings
from bot_service.integrations.agno_agent import create_llm_agent


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


redis_client = create_redis_client(settings.redis_url)
llm_agent = create_llm_agent(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    model=settings.llm_model_id,
)
