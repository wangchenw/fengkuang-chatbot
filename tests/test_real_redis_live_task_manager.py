import os
import uuid

import pytest
from redis.asyncio import Redis

from bot_service.services.live_task_manager import LiveTaskManager
from shared.redis_keys import bots_key, messages_key, state_key, stats_key, stop_key


pytestmark = pytest.mark.asyncio

REAL_REDIS_URL = os.getenv("REDIS_URL", "redis://101.133.133.237:6379/2")


def require_real_redis_tests() -> None:
    if os.getenv("RUN_REAL_REDIS_TESTS") != "1":
        pytest.skip("真实 Redis 测试默认跳过；设置 RUN_REAL_REDIS_TESTS=1 后执行")


@pytest.fixture
async def redis_client():
    require_real_redis_tests()
    client = Redis.from_url(
        REAL_REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    try:
        yield client
    finally:
        await client.aclose()


async def cleanup(redis_client: Redis, match_id: str) -> None:
    await redis_client.delete(
        state_key(match_id),
        bots_key(match_id),
        messages_key(match_id),
        stop_key(match_id),
        stats_key(match_id),
    )


async def test_real_redis_live_task_manager_start_write_stop_status(redis_client) -> None:
    match_id = f"test_{uuid.uuid4().hex}"
    manager = LiveTaskManager(redis_client)

    try:
        start_result = await manager.start_live(match_id, limit=2, now_ts=1717660800)
        message = await manager.write_one_fake_message(match_id, sequence=0, now_ts=1717660801)
        stop_result = await manager.stop_live(match_id)
        status = await manager.status_live(match_id)

        assert start_result["status"] == "running"
        assert start_result["bot_count"] == 2
        assert message.match_id == match_id
        assert message.bot_id == "bot_001"
        assert stop_result == {"match_id": match_id, "stop_requested": True}
        assert status["state"]["status"] == "running"
        assert status["state"]["bot_count"] == "2"
        assert status["stats"]["sent_total"] == "1"
        assert status["queue_len"] == 1
        assert status["stop_requested"] is True
    finally:
        await cleanup(redis_client, match_id)
