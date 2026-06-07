import json
import time

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from mock_live_room.api import pages
from mock_live_room.api.pages import get_redis_client
from mock_live_room.main import app
from shared.redis_keys import active_matches_key, context_key, messages_key, state_key, stats_key


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
    assert 'id="limit" name="limit" type="number" min="1" value="8"' in response.text
    assert 'href="/monitor"' in response.text
    assert "already_running" in response.text


async def test_room_page_renders_match_id(page_client) -> None:
    response = await page_client.get("/room", params={"matchId": "match_001"})

    assert response.status_code == 200
    assert "match_001" in response.text
    assert "formatMessageTime" in response.text
    assert "message.ts" in response.text
    assert "liveEvents" in response.text
    assert "loadLiveContext" in response.text
    assert "in_player_name" in response.text
    assert "out_player_name" in response.text
    assert "stage-events" in response.text
    assert "height: 100vh" in response.text
    assert "overflow: hidden" in response.text
    assert "minmax(0, 1fr)" in response.text
    assert 'limit: "50"' in response.text
    assert "<aside>\n    <div class=\"chat-head\">聊天</div>\n    <ul id=\"messages\">" in response.text


async def test_monitor_page_renders_monitor_controls(page_client) -> None:
    response = await page_client.get("/monitor")

    assert response.status_code == 200
    assert "监控管理" in response.text
    assert "monitorTable" in response.text
    assert "stopAllButton" in response.text
    assert "refreshInterval" in response.text


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


async def test_context_endpoint_returns_match_context(page_client, redis_client) -> None:
    context = {
        "source": "nanmi",
        "match_id": "match_001",
        "updated_at": 1717660800,
        "score": [4513032, 2, [1, 0, 0, 1, 3, 0, 0], [0, 0, 0, 2, 1, 0, 0], 0, ""],
        "stats": [{"type": 24, "home": 18, "away": 9}],
        "incidents": [{"type": 1, "position": 1, "time": 12, "home_score": 1, "away_score": 0}],
        "tlive": [{"time": "12'", "type": 1, "data": "主队取得进球", "position": 1, "main": 1}],
    }
    await redis_client.set(context_key("match_001"), json.dumps(context, ensure_ascii=False))

    response = await page_client.get("/api/context", params={"matchId": "match_001"})

    assert response.status_code == 200
    assert response.json()["match_id"] == "match_001"
    assert response.json()["context"]["source"] == "nanmi"
    assert response.json()["context"]["stats"][0]["type"] == 24


async def test_monitor_tasks_endpoint_returns_redis_task_snapshot(page_client, redis_client) -> None:
    now_ts = int(time.time())
    await redis_client.sadd(active_matches_key(), "match_001")
    await redis_client.hset(
        state_key("match_001"),
        mapping={
            "status": "running",
            "bot_count": "3",
            "started_at": str(now_ts - 720),
        },
    )
    await redis_client.hset(
        stats_key("match_001"),
        mapping={
            "sent_total": "12",
            "dedup_skip_total": "2",
            "llm_call_total": "5",
            "llm_error_total": "2",
            "token_input": "100",
            "token_output": "50",
        },
    )
    await redis_client.xadd(
        messages_key("match_001"),
        {
            "match_id": "match_001",
            "bot_id": "bot_001",
            "bot_name": "测试机器人",
            "content": "测试弹幕",
            "match_time": "实时",
            "event": "live",
            "ts": str(now_ts - 700),
        },
    )

    response = await page_client.get("/api/monitor/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["active_match_count"] == 1
    assert payload["summary"]["total_sent"] == 12
    assert payload["summary"]["token_total"] == 150
    assert payload["summary"]["llm_error_rate"] == 0.4
    assert payload["matches"][0]["match_id"] == "match_001"
    assert payload["matches"][0]["runtime_seconds"] >= 700
    assert payload["matches"][0]["bot_count"] == 3
    assert payload["matches"][0]["last_active_age_seconds"] >= 600
    assert "zombie_task" in payload["matches"][0]["warning_flags"]
    assert "high_error_rate" in payload["matches"][0]["warning_flags"]


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


async def test_monitor_stop_all_endpoint_stops_active_matches(page_client, redis_client, monkeypatch) -> None:
    calls = []

    async def fake_call_bot_service(path: str, params: dict[str, object]) -> dict[str, object]:
        calls.append((path, params))
        return {"path": path, "params": params}

    monkeypatch.setattr(pages, "call_bot_service", fake_call_bot_service)
    await redis_client.sadd(active_matches_key(), "match_001", "match_002")

    response = await page_client.post("/api/monitor/stopAll")

    assert response.status_code == 200
    assert response.json()["stopped_count"] == 2
    assert calls == [
        ("/stopLive", {"matchId": "match_001"}),
        ("/stopLive", {"matchId": "match_002"}),
    ]
