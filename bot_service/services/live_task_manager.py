import asyncio
import json
import time
from typing import Any

from redis.exceptions import ResponseError

from bot_service.personas.pool import get_personas
from bot_service.services.fake_message_generator import generate_fake_message
from bot_service.services.llm_message_generator import generate_llm_message
from shared.message_contract import ChatMessage
from shared.redis_keys import bots_key, messages_key, state_key, stats_key, stop_key


# 真实 Redis 客户端只要配置了 decode_responses=True，通常会直接返回 str。
# 这里仍然做一次轻量兼容，是因为 fakeredis 的部分命令（例如 hgetall、
# xinfo_groups）即使设置 decode_responses=True，也可能返回 bytes。
# 这样业务代码不用关心“真实 Redis”和“单元测试 Redis”的返回类型差异。
def _decode_redis_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_redis_hash(values: dict[Any, Any]) -> dict[str, str]:
    return {
        str(_decode_redis_value(key)): str(_decode_redis_value(value))
        for key, value in values.items()
    }


class LiveTaskManager:
    def __init__(
        self,
        redis_client: Any,
        consumer_group: str = "livestream-team",
        stream_maxlen: int = 5000,
        llm_agent: Any | None = None,
    ) -> None:
        self.redis = redis_client
        self.consumer_group = consumer_group
        self.stream_maxlen = stream_maxlen
        self.llm_agent = llm_agent

    async def start_live(
        self,
        match_id: str,
        limit: int,
        now_ts: int | None = None,
    ) -> dict[str, object]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        state = _decode_redis_hash(await self.redis.hgetall(state_key(match_id)))
        if state.get("status") == "running":
            return {
                "match_id": match_id,
                "status": "running",
                "bot_count": int(state.get("bot_count", "0")),
                "already_running": True,
            }

        started_at = now_ts if now_ts is not None else int(time.time())
        personas = get_personas(limit)

        await self.redis.delete(stop_key(match_id))
        await self.redis.hset(
            state_key(match_id),
            mapping={
                "status": "running",
                "bot_count": str(limit),
                "started_at": str(started_at),
            },
        )
        await self.redis.hset(
            bots_key(match_id),
            mapping={
                persona["bot_id"]: json.dumps(persona, ensure_ascii=False)
                for persona in personas
            },
        )
        await self.redis.hset(
            stats_key(match_id),
            mapping={
                "sent_total": "0",
            },
        )
        await self._ensure_consumer_group(match_id)

        return {
            "match_id": match_id,
            "status": "running",
            "bot_count": limit,
            "already_running": False,
        }

    async def stop_live(self, match_id: str) -> dict[str, object]:
        await self.redis.set(stop_key(match_id), "1")
        return {"match_id": match_id, "stop_requested": True}

    async def status_live(self, match_id: str) -> dict[str, object]:
        return {
            "match_id": match_id,
            "state": _decode_redis_hash(await self.redis.hgetall(state_key(match_id))),
            "stats": _decode_redis_hash(await self.redis.hgetall(stats_key(match_id))),
            "queue_len": await self.redis.xlen(messages_key(match_id)),
            "stop_requested": bool(await self.redis.exists(stop_key(match_id))),
        }

    async def write_one_fake_message(
        self,
        match_id: str,
        sequence: int = 0,
        now_ts: int | None = None,
    ) -> ChatMessage:
        bot = await self._get_bot_for_sequence(match_id, sequence)
        message = generate_fake_message(match_id, bot, sequence, now_ts=now_ts)

        await self.redis.xadd(
            messages_key(match_id),
            message.to_redis_fields(),
            maxlen=self.stream_maxlen,
            approximate=True,
        )
        await self.redis.hincrby(stats_key(match_id), "sent_total", 1)

        return message

    async def write_one_message(
        self,
        match_id: str,
        sequence: int = 0,
        now_ts: int | None = None,
    ) -> ChatMessage:
        if self.llm_agent is None:
            return await self.write_one_fake_message(match_id, sequence=sequence, now_ts=now_ts)

        bot = await self._get_bot_for_sequence(match_id, sequence)
        message = await generate_llm_message(
            match_id=match_id,
            bot=bot,
            sequence=sequence,
            llm_agent=self.llm_agent,
            now_ts=now_ts,
        )

        await self.redis.xadd(
            messages_key(match_id),
            message.to_redis_fields(),
            maxlen=self.stream_maxlen,
            approximate=True,
        )
        await self.redis.hincrby(stats_key(match_id), "sent_total", 1)

        return message

    async def run_fake_message_loop(
        self,
        match_id: str,
        interval_seconds: float = 3.0,
    ) -> None:
        sequence = 0
        while not await self.redis.exists(stop_key(match_id)):
            await self.write_one_message(match_id, sequence=sequence)
            sequence += 1
            await asyncio.sleep(interval_seconds)

    async def _ensure_consumer_group(self, match_id: str) -> None:
        try:
            await self.redis.xgroup_create(
                name=messages_key(match_id),
                groupname=self.consumer_group,
                id="$",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _get_bot_for_sequence(self, match_id: str, sequence: int) -> dict[str, str]:
        bots = _decode_redis_hash(await self.redis.hgetall(bots_key(match_id)))
        if not bots:
            raise ValueError(f"match {match_id} has no bots")

        bot_ids = sorted(bots)
        bot_id = bot_ids[sequence % len(bot_ids)]
        return json.loads(bots[bot_id])
