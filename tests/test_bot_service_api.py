import asyncio

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from bot_service.api.live import (
    cancel_all_fake_loops,
    get_live_task_manager,
    get_message_interval_seconds,
)
from bot_service.main import app
from bot_service.services.live_task_manager import LiveTaskManager
from shared.redis_keys import messages_key, state_key, stop_key


pytestmark = pytest.mark.asyncio


async def wait_until(condition, timeout: float = 1.0, interval: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await condition():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition was not met before timeout")


@pytest.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def api_client(redis_client):
    app.dependency_overrides[get_live_task_manager] = lambda: LiveTaskManager(redis_client)
    app.dependency_overrides[get_message_interval_seconds] = lambda: 0.01
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    await cancel_all_fake_loops()
    app.dependency_overrides.clear()


async def test_start_live_endpoint_starts_match(api_client, redis_client) -> None:
    response = await api_client.get("/startLive", params={"matchId": "match_001", "limit": 2})

    assert response.status_code == 200
    assert response.json() == {
        "match_id": "match_001",
        "status": "running",
        "bot_count": 2,
        "already_running": False,
    }
    assert await redis_client.hget(state_key("match_001"), "status") == "running"


async def test_start_live_endpoint_is_idempotent(api_client) -> None:
    first = await api_client.get("/startLive", params={"matchId": "match_001", "limit": 2})
    second = await api_client.get("/startLive", params={"matchId": "match_001", "limit": 9})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["already_running"] is True
    assert second.json()["bot_count"] == 2


async def test_start_live_endpoint_rejects_invalid_limit(api_client) -> None:
    response = await api_client.get("/startLive", params={"matchId": "match_001", "limit": 0})

    assert response.status_code == 422


async def test_stop_live_endpoint_writes_stop_signal(api_client, redis_client) -> None:
    response = await api_client.get("/stopLive", params={"matchId": "match_001"})

    assert response.status_code == 200
    assert response.json() == {"match_id": "match_001", "stop_requested": True}
    assert await redis_client.get(stop_key("match_001")) == "1"


async def test_status_live_endpoint_returns_match_status(api_client) -> None:
    await api_client.get("/startLive", params={"matchId": "match_001", "limit": 1})
    response = await api_client.get("/statusLive", params={"matchId": "match_001"})

    assert response.status_code == 200
    data = response.json()
    assert data["match_id"] == "match_001"
    assert data["state"]["status"] == "running"
    assert data["state"]["bot_count"] == "1"
    assert data["queue_len"] >= 0
    assert data["stop_requested"] is False


async def test_start_live_endpoint_starts_background_fake_message_loop(
    api_client,
    redis_client,
) -> None:
    response = await api_client.get("/startLive", params={"matchId": "match_001", "limit": 1})

    assert response.status_code == 200

    await wait_until(
        lambda: redis_client.xlen(messages_key("match_001")),
        timeout=1.0,
    )

    assert await redis_client.xlen(messages_key("match_001")) >= 1

    await api_client.get("/stopLive", params={"matchId": "match_001"})
