import pytest
from fakeredis.aioredis import FakeRedis

from mock_live_room.consumers.redis_stream_consumer import read_recent_messages
from shared.redis_keys import messages_key


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def test_read_recent_messages_returns_latest_messages_in_chronological_order(redis_client) -> None:
    stream = messages_key("match_001")
    for index in range(3):
        await redis_client.xadd(
            stream,
            {
                "match_id": "match_001",
                "bot_id": f"bot_{index}",
                "bot_name": "测试机器人",
                "content": f"第{index}条消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(index),
            },
        )

    messages = await read_recent_messages(redis_client, "match_001", limit=2)

    assert [message["content"] for message in messages] == ["第1条消息", "第2条消息"]


async def test_read_recent_messages_keeps_latest_50_by_default(redis_client) -> None:
    stream = messages_key("match_001")
    for index in range(60):
        await redis_client.xadd(
            stream,
            {
                "match_id": "match_001",
                "bot_id": f"bot_{index}",
                "bot_name": "测试机器人",
                "content": f"第{index}条消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(index),
            },
        )

    messages = await read_recent_messages(redis_client, "match_001")

    assert len(messages) == 50
    assert messages[0]["content"] == "第10条消息"
    assert messages[-1]["content"] == "第59条消息"


async def test_read_recent_messages_returns_empty_list_when_stream_missing(redis_client) -> None:
    messages = await read_recent_messages(redis_client, "missing_match", limit=20)

    assert messages == []
