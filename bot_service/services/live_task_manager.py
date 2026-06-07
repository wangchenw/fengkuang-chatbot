import asyncio
import json
import logging
import time
from typing import Any

from redis.exceptions import ResponseError

from bot_service.personas.pool import get_personas
from bot_service.services.fake_message_generator import generate_fake_message
from bot_service.services.llm_message_generator import generate_llm_message_with_usage
from bot_service.services.match_context_store import (
    add_active_match,
    read_match_context,
    remove_active_match,
)
from shared.message_contract import ChatMessage
from shared.redis_keys import bots_key, messages_key, state_key, stats_key, stop_key

TERMINAL_MATCH_STATUSES = {8, 11, 12}
logger = logging.getLogger(__name__)


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


def _is_terminal_match_context(match_context: dict[str, Any] | None) -> bool:
    return match_context is not None and match_context["score"][1] in TERMINAL_MATCH_STATUSES


class LiveTaskManager:
    def __init__(
        self,
        redis_client: Any,
        consumer_group: str = "livestream-team",
        stream_maxlen: int = 5000,
        llm_agent: Any | None = None,
        match_ttl_seconds: int = 86400,
        max_runtime_seconds: int = 14400,
    ) -> None:
        self.redis = redis_client
        self.consumer_group = consumer_group
        self.stream_maxlen = stream_maxlen
        self.llm_agent = llm_agent
        self.match_ttl_seconds = match_ttl_seconds
        self.max_runtime_seconds = max_runtime_seconds

    async def start_live(
        self,
        match_id: str,
        limit: int,
        now_ts: int | None = None,
    ) -> dict[str, object]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        state = _decode_redis_hash(await self.redis.hgetall(state_key(match_id)))
        stop_requested = bool(await self.redis.exists(stop_key(match_id)))
        if state.get("status") == "running" and not stop_requested:
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
                "dedup_skip_total": "0",
                "llm_call_total": "0",
                "llm_error_total": "0",
                "token_input": "0",
                "token_output": "0",
            },
        )
        await self._ensure_consumer_group(match_id)
        await self._refresh_match_ttl(match_id)

        # 把比赛id添加到 纳米数据监听服务中，去缓存该场比赛数据
        await add_active_match(self.redis, match_id)

        return {
            "match_id": match_id,
            "status": "running",
            "bot_count": limit,
            "already_running": False,
        }

    async def stop_live(self, match_id: str) -> dict[str, object]:
        await self.redis.set(stop_key(match_id), "1")
        await self._refresh_match_ttl(match_id)
        # 把比赛id从 纳米数据监听服务中移除
        await remove_active_match(self.redis, match_id)
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
        await self._refresh_match_ttl(match_id)

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
        match_context = await read_match_context(self.redis, match_id)
        started_at = time.perf_counter()

        logger.info(
            "LLM message generation started match_id=%s bot_id=%s bot_name=%s sequence=%s has_context=%s",
            match_id,
            bot["bot_id"],
            bot["name"],
            sequence,
            match_context is not None,
        )

        try:
            await self.redis.hincrby(stats_key(match_id), "llm_call_total", 1)
            message, token_usage = await generate_llm_message_with_usage(
                match_id=match_id,
                bot=bot,
                sequence=sequence,
                llm_agent=self.llm_agent,
                now_ts=now_ts,
                match_context=match_context,
            )
        except Exception:
            await self.redis.hincrby(stats_key(match_id), "llm_error_total", 1)
            await self._refresh_match_ttl(match_id)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception(
                "LLM message generation failed match_id=%s bot_id=%s bot_name=%s sequence=%s elapsed_ms=%s",
                match_id,
                bot["bot_id"],
                bot["name"],
                sequence,
                elapsed_ms,
            )
            raise

        input_tokens, output_tokens = token_usage
        if input_tokens:
            await self.redis.hincrby(stats_key(match_id), "token_input", input_tokens)
        if output_tokens:
            await self.redis.hincrby(stats_key(match_id), "token_output", output_tokens)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "LLM message generation finished match_id=%s bot_id=%s bot_name=%s sequence=%s elapsed_ms=%s content_chars=%s",
            match_id,
            bot["bot_id"],
            bot["name"],
            sequence,
            elapsed_ms,
            len(message.content),
        )

        await self.redis.xadd(
            messages_key(match_id),
            message.to_redis_fields(),
            maxlen=self.stream_maxlen,
            approximate=True,
        )
        await self.redis.hincrby(stats_key(match_id), "sent_total", 1)
        await self._refresh_match_ttl(match_id)

        return message

    async def run_fake_message_loop(
        self,
        match_id: str,
        interval_seconds: float = 3.0,
    ) -> None:
        sequence = 0
        while not await self.redis.exists(stop_key(match_id)):
            
            if await self._stop_if_match_finished(match_id):
                break

            if await self._stop_if_runtime_exceeded(match_id):
                break

            await self.write_one_message(match_id, sequence=sequence)
            sequence += 1
            await asyncio.sleep(interval_seconds)

    async def _stop_if_match_finished(self, match_id: str) -> bool:
        match_context = await read_match_context(self.redis, match_id)
        if not _is_terminal_match_context(match_context):
            return False

        await self.redis.set(stop_key(match_id), "1")
        await self._refresh_match_ttl(match_id)
        await remove_active_match(self.redis, match_id)
        return True

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

    async def _refresh_match_ttl(self, match_id: str) -> None:
        for key in (
            state_key(match_id),
            bots_key(match_id),
            stats_key(match_id),
            messages_key(match_id),
            stop_key(match_id),
        ):
            if await self.redis.exists(key):
                await self.redis.expire(key, self.match_ttl_seconds)

    async def _get_bot_for_sequence(self, match_id: str, sequence: int) -> dict[str, str]:
        bots = _decode_redis_hash(await self.redis.hgetall(bots_key(match_id)))
        if not bots:
            raise ValueError(f"match {match_id} has no bots")

        bot_ids = sorted(bots)
        bot_id = bot_ids[sequence % len(bot_ids)]
        return json.loads(bots[bot_id])

    async def _stop_if_runtime_exceeded(self, match_id: str) -> bool:
        state = _decode_redis_hash(await self.redis.hgetall(state_key(match_id)))
        started_at = int(state.get("started_at", "0") or 0)
        if started_at <= 0:
            return False

        runtime_seconds = int(time.time()) - started_at
        if runtime_seconds <= self.max_runtime_seconds:
            return False

        await self.redis.set(stop_key(match_id), "1")
        await self._refresh_match_ttl(match_id)
        await remove_active_match(self.redis, match_id)
        logger.warning(
            "Live task auto stopped because runtime exceeded match_id=%s runtime_seconds=%s max_runtime_seconds=%s",
            match_id,
            runtime_seconds,
            self.max_runtime_seconds,
        )
        return True