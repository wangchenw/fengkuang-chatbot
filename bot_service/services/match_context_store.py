import json
from typing import Any

from shared.redis_keys import active_matches_key, context_key

def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value

async def add_active_match(redis_client: Any, match_id: str) -> None:
    await redis_client.sadd(active_matches_key(), str(match_id))

async def remove_active_match(redis_client: Any, match_id: str) -> None:
    await redis_client.srem(active_matches_key(), str(match_id))

async def get_active_match_ids(redis_client: Any) -> set[str]:
    values = await redis_client.smembers(active_matches_key())
    return {str(_decode(value)) for value in values}


async def write_match_context(
    redis_client: Any, 
    match_id: str, 
    context: dict[str, Any], 
    ttl_seconds: int ) -> None:

    await redis_client.set(
        context_key(match_id), 
        json.dumps(context, ensure_ascii=False),
        ex=ttl_seconds,
    )

async def read_match_context(redis_client: Any, match_id: str) -> dict[str, Any]:
    raw = await redis_client.get(context_key(match_id))
    if not raw:
        return None

    try:
        return json.loads(str(_decode(raw)))
    except json.JSONDecodeError:
        return None



     