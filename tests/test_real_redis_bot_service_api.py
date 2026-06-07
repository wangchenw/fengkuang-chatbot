import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from bot_service.main import app
from shared.redis_keys import bots_key, messages_key, state_key, stats_key, stop_key


pytestmark = pytest.mark.asyncio

REAL_REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/2")


def require_real_redis_tests() -> None:
    if os.getenv("RUN_REAL_REDIS_TESTS") != "1":
        pytest.skip("本地 Redis 测试默认跳过；设置 RUN_REAL_REDIS_TESTS=1 后执行")


async def cleanup(match_id: str) -> None:
    client = Redis.from_url(
        REAL_REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    try:
        await client.delete(
            state_key(match_id),
            bots_key(match_id),
            messages_key(match_id),
            stop_key(match_id),
            stats_key(match_id),
        )
    finally:
        await client.aclose()


async def test_real_redis_bot_service_api_start_status_stop() -> None:
    require_real_redis_tests()
    match_id = f"test_{uuid.uuid4().hex}"
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            start_response = await client.get("/startLive", params={"matchId": match_id, "limit": 2})
            status_response = await client.get("/statusLive", params={"matchId": match_id})
            stop_response = await client.get("/stopLive", params={"matchId": match_id})
            stopped_status_response = await client.get("/statusLive", params={"matchId": match_id})

        assert start_response.status_code == 200
        assert start_response.json()["status"] == "running"
        assert start_response.json()["bot_count"] == 2
        assert status_response.json()["state"]["status"] == "running"
        assert status_response.json()["state"]["bot_count"] == "2"
        assert stop_response.json() == {"match_id": match_id, "stop_requested": True}
        assert stopped_status_response.json()["stop_requested"] is True
    finally:
        await cleanup(match_id)
