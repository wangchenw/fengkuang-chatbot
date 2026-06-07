import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from mock_live_room.api import pages
from mock_live_room.api.pages import get_redis_client
from mock_live_room.main import app
from shared.redis_keys import messages_key


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def page_client(redis_client, monkeypatch):
    async def fake_call_bot_service(path: str, params: dict[str, object]) -> dict[str, object]:
        return {"path": path, "params": params}

    monkeypatch.setattr(pages, "call_bot_service", fake_call_bot_service)
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


async def test_index_page_renders_control_form(page_client) -> None:
    response = await page_client.get("/")

    assert response.status_code == 200
    assert "模拟直播间" in response.text
    assert "matchId" in response.text
    assert "limit" in response.text


async def test_room_page_renders_match_id(page_client) -> None:
    response = await page_client.get("/room", params={"matchId": "match_001"})

    assert response.status_code == 200
    assert "match_001" in response.text


async def test_messages_endpoint_returns_stream_messages(page_client, redis_client) -> None:
    await redis_client.xadd(
        messages_key("match_001"),
        {
            "match_id": "match_001",
            "bot_id": "bot_001",
            "bot_name": "测试机器人",
            "content": "这波进攻有点意思",
            "match_time": "测试时间",
            "event": "测试事件",
            "ts": "1717660800",
        },
    )

    response = await page_client.get("/api/messages", params={"matchId": "match_001"})

    assert response.status_code == 200
    assert response.json()["messages"][0]["content"] == "这波进攻有点意思"


async def test_start_endpoint_proxies_to_bot_service(page_client) -> None:
    response = await page_client.get("/api/start", params={"matchId": "match_001", "limit": 2})

    assert response.status_code == 200
    assert response.json() == {
        "path": "/startLive",
        "params": {"matchId": "match_001", "limit": 2},
    }


async def test_stop_endpoint_proxies_to_bot_service(page_client) -> None:
    response = await page_client.get("/api/stop", params={"matchId": "match_001"})

    assert response.status_code == 200
    assert response.json() == {
        "path": "/stopLive",
        "params": {"matchId": "match_001"},
    }
