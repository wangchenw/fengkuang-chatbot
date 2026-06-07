import time
from typing import Any

from bot_service.services.match_context_store import get_active_match_ids
from shared.redis_keys import messages_key, state_key, stats_key


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_hash(values: dict[Any, Any]) -> dict[str, str]:
    return {
        str(_decode(key)): str(_decode(value))
        for key, value in values.items()
    }


def _int_value(values: dict[str, str], key: str) -> int:
    raw = values.get(key)
    if raw in (None, ""):
        return 0
    return int(raw)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _warning_flags(
    status: str,
    runtime_seconds: int,
    last_active_age_seconds: int | None,
    llm_call_total: int,
    llm_error_total: int,
    stream_length: int,
) -> list[str]:
    flags = []
    if status == "running" and last_active_age_seconds is not None and last_active_age_seconds > 600:
        flags.append("zombie_task")
    if runtime_seconds > 14400:
        flags.append("long_running")
    if llm_call_total > 0 and llm_error_total / llm_call_total > 0.2:
        flags.append("high_error_rate")
    if stream_length > 1000:
        flags.append("stream_backlog")
    return flags


async def _last_message_ts(redis_client: Any, match_id: str) -> int | None:
    rows = await redis_client.xrevrange(messages_key(match_id), count=1)
    if not rows:
        return None

    _, fields = rows[0]
    decoded = _decode_hash(fields)
    raw_ts = decoded.get("ts")
    return int(raw_ts) if raw_ts else None


async def build_monitor_snapshot(redis_client: Any, now_ts: int | None = None) -> dict[str, Any]:
    current_ts = now_ts if now_ts is not None else int(time.time())
    match_ids = sorted(await get_active_match_ids(redis_client))
    matches = []

    for match_id in match_ids:
        state = _decode_hash(await redis_client.hgetall(state_key(match_id)))
        stats = _decode_hash(await redis_client.hgetall(stats_key(match_id)))

        started_at = _int_value(state, "started_at")
        runtime_seconds = max(current_ts - started_at, 0) if started_at else 0
        stream_length = await redis_client.xlen(messages_key(match_id))
        last_active_ts = await _last_message_ts(redis_client, match_id)
        last_active_age_seconds = (
            max(current_ts - last_active_ts, 0)
            if last_active_ts is not None
            else None
        )

        llm_call_total = _int_value(stats, "llm_call_total")
        llm_error_total = _int_value(stats, "llm_error_total")
        token_input = _int_value(stats, "token_input")
        token_output = _int_value(stats, "token_output")
        status = state.get("status", "unknown")

        matches.append(
            {
                "match_id": match_id,
                "status": status,
                "runtime_seconds": runtime_seconds,
                "bot_count": _int_value(state, "bot_count"),
                "sent_total": _int_value(stats, "sent_total"),
                "dedup_skip_total": _int_value(stats, "dedup_skip_total"),
                "llm_call_total": llm_call_total,
                "llm_error_total": llm_error_total,
                "llm_error_rate": _rate(llm_error_total, llm_call_total),
                "token_input": token_input,
                "token_output": token_output,
                "token_total": token_input + token_output,
                "stream_length": stream_length,
                "last_active_ts": last_active_ts,
                "last_active_age_seconds": last_active_age_seconds,
                "warning_flags": _warning_flags(
                    status=status,
                    runtime_seconds=runtime_seconds,
                    last_active_age_seconds=last_active_age_seconds,
                    llm_call_total=llm_call_total,
                    llm_error_total=llm_error_total,
                    stream_length=stream_length,
                ),
            }
        )

    total_calls = sum(item["llm_call_total"] for item in matches)
    total_errors = sum(item["llm_error_total"] for item in matches)
    return {
        "updated_at": current_ts,
        "summary": {
            "active_match_count": sum(1 for item in matches if item["status"] == "running"),
            "total_sent": sum(item["sent_total"] for item in matches),
            "token_total": sum(item["token_total"] for item in matches),
            "llm_call_total": total_calls,
            "llm_error_total": total_errors,
            "llm_error_rate": _rate(total_errors, total_calls),
        },
        "matches": matches,
    }
