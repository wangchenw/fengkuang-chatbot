import json
import asyncio
import logging
import time

import pytest
from fakeredis.aioredis import FakeRedis

from bot_service.services.live_task_manager import LiveTaskManager
from shared.redis_keys import active_matches_key, bots_key, context_key, messages_key, state_key, stats_key, stop_key


pytestmark = pytest.mark.asyncio


async def wait_until(condition, timeout: float = 1.0, interval: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await condition():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition was not met before timeout")


def decode_hash(values: dict[object, object]) -> dict[str, str]:
    decoded = {}
    for key, value in values.items():
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        decoded[str(key)] = str(value)
    return decoded


@pytest.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def test_start_live_writes_state_bots_and_consumer_group(redis_client) -> None:
    manager = LiveTaskManager(redis_client, match_ttl_seconds=86400)

    result = await manager.start_live(
        match_id="match_001",
        limit=2,
        now_ts=1717660800,
    )

    assert result == {
        "match_id": "match_001",
        "status": "running",
        "bot_count": 2,
        "already_running": False,
    }

    state = decode_hash(await redis_client.hgetall(state_key("match_001")))
    assert state == {
        "status": "running",
        "bot_count": "2",
        "started_at": "1717660800",
    }

    bots = decode_hash(await redis_client.hgetall(bots_key("match_001")))
    assert sorted(bots) == ["bot_001", "bot_002"]
    assert json.loads(bots["bot_001"])["name"] == "热血球迷1"

    groups = await redis_client.xinfo_groups(messages_key("match_001"))
    group_name = groups[0]["name"]
    if isinstance(group_name, bytes):
        group_name = group_name.decode("utf-8")
    assert group_name == "livestream-team"
    assert await redis_client.ttl(state_key("match_001")) == 86400
    assert await redis_client.ttl(bots_key("match_001")) == 86400
    assert await redis_client.ttl(stats_key("match_001")) == 86400
    assert await redis_client.ttl(messages_key("match_001")) == 86400


async def test_start_live_is_idempotent_for_running_match(redis_client) -> None:
    manager = LiveTaskManager(redis_client)

    first = await manager.start_live("match_001", limit=2, now_ts=1717660800)
    second = await manager.start_live("match_001", limit=9, now_ts=1717660900)

    assert first["already_running"] is False
    assert second == {
        "match_id": "match_001",
        "status": "running",
        "bot_count": 2,
        "already_running": True,
    }

    state = decode_hash(await redis_client.hgetall(state_key("match_001")))
    assert state["bot_count"] == "2"
    assert state["started_at"] == "1717660800"


async def test_start_live_clears_old_stop_signal(redis_client) -> None:
    manager = LiveTaskManager(redis_client)
    await redis_client.set(stop_key("match_001"), "1")

    await manager.start_live("match_001", limit=1, now_ts=1717660800)

    assert await redis_client.exists(stop_key("match_001")) == 0


async def test_start_live_restarts_running_match_with_stop_signal(redis_client) -> None:
    manager = LiveTaskManager(redis_client)
    await manager.start_live("match_001", limit=1, now_ts=1717660800)
    await manager.write_one_fake_message("match_001", sequence=0, now_ts=1717660801)
    await manager.stop_live("match_001")

    result = await manager.start_live("match_001", limit=3, now_ts=1717660900)

    state = decode_hash(await redis_client.hgetall(state_key("match_001")))
    stats = decode_hash(await redis_client.hgetall(stats_key("match_001")))
    assert result == {
        "match_id": "match_001",
        "status": "running",
        "bot_count": 3,
        "already_running": False,
    }
    assert await redis_client.exists(stop_key("match_001")) == 0
    assert state["bot_count"] == "3"
    assert state["started_at"] == "1717660900"
    assert stats["sent_total"] == "0"


async def test_start_live_rejects_non_positive_limit(redis_client) -> None:
    manager = LiveTaskManager(redis_client)

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await manager.start_live("match_001", limit=0, now_ts=1717660800)


async def test_stop_live_writes_stop_signal(redis_client) -> None:
    manager = LiveTaskManager(redis_client, match_ttl_seconds=86400)

    result = await manager.stop_live("match_001")

    assert result == {"match_id": "match_001", "stop_requested": True}
    assert await redis_client.get(stop_key("match_001")) == "1"
    assert await redis_client.ttl(stop_key("match_001")) == 86400


async def test_status_live_returns_state_stats_queue_and_stop_flag(redis_client) -> None:
    manager = LiveTaskManager(redis_client)
    await manager.start_live("match_001", limit=1, now_ts=1717660800)
    await manager.write_one_fake_message("match_001", sequence=0, now_ts=1717660801)
    await manager.stop_live("match_001")

    status = await manager.status_live("match_001")

    assert status["match_id"] == "match_001"
    assert status["state"]["status"] == "running"
    assert status["state"]["bot_count"] == "1"
    assert status["stats"]["sent_total"] == "1"
    assert status["queue_len"] == 1
    assert status["stop_requested"] is True


async def test_write_one_fake_message_writes_stream_and_updates_stats(redis_client) -> None:
    manager = LiveTaskManager(redis_client, match_ttl_seconds=86400)
    await manager.start_live("match_001", limit=1, now_ts=1717660800)

    message = await manager.write_one_fake_message(
        "match_001",
        sequence=0,
        now_ts=1717660801,
    )

    rows = await redis_client.xrange(messages_key("match_001"), min="-", max="+")
    _, fields = rows[0]

    assert message.content == "这比赛节奏起来了"
    assert fields["match_id"] == "match_001"
    assert fields["bot_id"] == "bot_001"
    assert fields["bot_name"] == "热血球迷1"
    assert fields["content"] == "这比赛节奏起来了"
    assert fields["ts"] == "1717660801"
    assert await redis_client.hget(stats_key("match_001"), "sent_total") == "1"
    assert await redis_client.ttl(messages_key("match_001")) == 86400
    assert await redis_client.ttl(stats_key("match_001")) == 86400


async def test_write_one_message_uses_llm_agent_when_provided(redis_client) -> None:
    class FakeAgentResponse:
        content = "LLM生成的弹幕"

    class FakeAgent:
        async def arun(self, input, **kwargs) -> FakeAgentResponse:
            return FakeAgentResponse()

    manager = LiveTaskManager(redis_client, llm_agent=FakeAgent())
    await manager.start_live("match_001", limit=1, now_ts=1717660800)

    message = await manager.write_one_message(
        "match_001",
        sequence=0,
        now_ts=1717660801,
    )

    rows = await redis_client.xrange(messages_key("match_001"), min="-", max="+")
    _, fields = rows[0]

    assert message.content == "LLM生成的弹幕"
    assert fields["content"] == "LLM生成的弹幕"


async def test_write_one_message_logs_paid_llm_generation(redis_client, caplog) -> None:
    class FakeAgentResponse:
        content = "LLM生成的弹幕"

    class FakeAgent:
        async def arun(self, input, **kwargs) -> FakeAgentResponse:
            return FakeAgentResponse()

    manager = LiveTaskManager(redis_client, llm_agent=FakeAgent())
    await manager.start_live("match_001", limit=1, now_ts=1717660800)

    with caplog.at_level(logging.INFO, logger="bot_service.services.live_task_manager"):
        await manager.write_one_message(
            "match_001",
            sequence=0,
            now_ts=1717660801,
        )

    messages = [record.message for record in caplog.records]
    assert any("LLM message generation started" in message for message in messages)
    assert any("LLM message generation finished" in message for message in messages)
    assert all("content=" not in message for message in messages)


async def test_write_one_message_tracks_llm_calls_and_token_usage(redis_client) -> None:
    class FakeAgentResponse:
        content = "LLM生成的弹幕"
        usage = {"prompt_tokens": 7, "completion_tokens": 3}

    class FakeAgent:
        async def arun(self, input, **kwargs) -> FakeAgentResponse:
            return FakeAgentResponse()

    manager = LiveTaskManager(redis_client, llm_agent=FakeAgent())
    await manager.start_live("match_001", limit=1, now_ts=1717660800)

    await manager.write_one_message(
        "match_001",
        sequence=0,
        now_ts=1717660801,
    )

    stats = decode_hash(await redis_client.hgetall(stats_key("match_001")))
    assert stats["llm_call_total"] == "1"
    assert stats["llm_error_total"] == "0"
    assert stats["token_input"] == "7"
    assert stats["token_output"] == "3"


async def test_write_one_message_tracks_llm_errors(redis_client) -> None:
    class FailingAgent:
        async def arun(self, input, **kwargs) -> str:
            raise RuntimeError("LLM failed")

    manager = LiveTaskManager(redis_client, llm_agent=FailingAgent(), match_ttl_seconds=86400)
    await manager.start_live("match_001", limit=1, now_ts=1717660800)

    with pytest.raises(RuntimeError, match="LLM failed"):
        await manager.write_one_message(
            "match_001",
            sequence=0,
            now_ts=1717660801,
        )

    stats = decode_hash(await redis_client.hgetall(stats_key("match_001")))
    assert stats["llm_call_total"] == "1"
    assert stats["llm_error_total"] == "1"
    assert await redis_client.xlen(messages_key("match_001")) == 0
    assert await redis_client.ttl(stats_key("match_001")) == 86400


async def test_run_fake_message_loop_writes_until_stop_signal(redis_client) -> None:
    manager = LiveTaskManager(redis_client)
    await manager.start_live("match_001", limit=1, now_ts=int(time.time()) - 60)

    task = asyncio.create_task(
        manager.run_fake_message_loop(
            "match_001",
            interval_seconds=0.01,
        )
    )

    try:
        await wait_until(
            lambda: redis_client.xlen(messages_key("match_001")),
            timeout=1.0,
        )
        assert await redis_client.xlen(messages_key("match_001")) >= 1

        await manager.stop_live("match_001")
        await asyncio.wait_for(task, timeout=1.0)

        assert task.done()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_run_fake_message_loop_stops_when_runtime_exceeded(redis_client) -> None:
    manager = LiveTaskManager(
        redis_client,
        match_ttl_seconds=86400,
        max_runtime_seconds=14400,
    )
    await manager.start_live("match_001", limit=1, now_ts=int(time.time()) - 14401)

    await manager.run_fake_message_loop(
        "match_001",
        interval_seconds=0.01,
    )

    assert await redis_client.xlen(messages_key("match_001")) == 0
    assert await redis_client.get(stop_key("match_001")) == "1"
    assert await redis_client.smembers(active_matches_key()) == set()
    assert await redis_client.ttl(stop_key("match_001")) == 86400


async def test_run_fake_message_loop_stops_when_match_context_is_finished(redis_client) -> None:
    manager = LiveTaskManager(redis_client)
    await manager.start_live("match_001", limit=1, now_ts=1717660800)
    await redis_client.set(
        context_key("match_001"),
        json.dumps(
            {
                "source": "nami",
                "match_id": "match_001",
                "score": [4513032, 8, [1, 0, 0, 0, -1, 0, 0], [1, 0, 0, 0, -1, 0, 0], 0, ""],
                "stats": [],
                "incidents": [],
                "tlive": [],
            },
            ensure_ascii=False,
        ),
    )

    task = asyncio.create_task(
        manager.run_fake_message_loop(
            "match_001",
            interval_seconds=0.01,
        )
    )

    try:
        await asyncio.wait_for(task, timeout=1.0)

        assert await redis_client.xlen(messages_key("match_001")) == 0
        assert await redis_client.get(stop_key("match_001")) == "1"
        assert await redis_client.smembers(active_matches_key()) == set()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
