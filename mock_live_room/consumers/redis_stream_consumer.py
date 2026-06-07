from typing import Any

from shared.redis_keys import messages_key


def _decode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_message(fields: dict[Any, Any]) -> dict[str, str]:
    return {
        str(_decode_value(key)): str(_decode_value(value))
        for key, value in fields.items()
    }


async def read_recent_messages(
    redis_client: Any,
    match_id: str,
    limit: int = 50,
) -> list[dict[str, str]]:
    rows = await redis_client.xrevrange(
        messages_key(match_id),
        max="+",
        min="-",
        count=limit,
    )
    return [
        _decode_message(fields)
        for _, fields in reversed(rows)
    ]
