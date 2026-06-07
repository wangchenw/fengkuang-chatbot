import asyncio
import logging
import time
from typing import Any

from bot_service.integrations.nami_client import NamiLiveClient
from bot_service.services.match_context_store import get_active_match_ids, remove_active_match, write_match_context
from shared.redis_keys import stats_key, stop_key


logger = logging.getLogger(__name__)
TERMINAL_MATCH_STATUSES = {8, 11, 12}


def is_terminal_score(score: list[Any]) -> bool:
    return score[1] in TERMINAL_MATCH_STATUSES


def build_match_context(raw_match: dict[str, Any], now_ts: int) -> dict[str, Any]:
    return {
        "source": "nami",
        "match_id": str(raw_match.get("id")),
        "updated_at": now_ts,
        "score": raw_match.get("score"),
        "stats": raw_match.get("stats", []),
        "incidents": raw_match.get("incidents", []),
        "tlive": raw_match.get("tlive", []),
    }

class NamiLivePoller:
    def __init__(
        self,
        redis_client: Any,
        nami_client: NamiLiveClient,
        poll_interval_seconds: float = 2.0,
        context_ttl_seconds: int = 7200,
        match_ttl_seconds: int = 86400,
    ) -> None:
        self.redis = redis_client
        self.nami_client = nami_client
        self.poll_interval_seconds = poll_interval_seconds
        self.context_ttl_seconds = context_ttl_seconds
        self.match_ttl_seconds = match_ttl_seconds

    async def run_once(self) -> dict[str, int]:
        active_match_ids = await get_active_match_ids(self.redis)
        if not active_match_ids:
            return {"active_count": 0, "updated_count": 0}
            
        matches = await self.nami_client.fetch_live_matches()
        matches_by_id = {
            str(match["id"]): match
            for match in matches
            if match.get("id") is not None
        }

        now_ts = int(time.time())
        updated_count = 0

        for match_id in active_match_ids:
            raw_match = matches_by_id.get(match_id)
            if raw_match is None:
                continue

            context = build_match_context(raw_match, now_ts)
            await write_match_context(
                self.redis,
                match_id,
                context,
                ttl_seconds=self.context_ttl_seconds,
            )

            await self.redis.hset(
                stats_key(match_id),
                mapping={
                    "context_updated_at": str(now_ts),
                    "nami_last_seen_at": str(now_ts),
                },
            )
            await self.redis.expire(stats_key(match_id), self.match_ttl_seconds)
            if is_terminal_score(context["score"]):
                await self.redis.set(stop_key(match_id), "1")
                await self.redis.expire(stop_key(match_id), self.match_ttl_seconds)
                await remove_active_match(self.redis, match_id)

            updated_count += 1

        return {"active_count": len(active_match_ids), "updated_count": updated_count}

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Error 获取 Nami 数据失败。")
            await asyncio.sleep(self.poll_interval_seconds)
