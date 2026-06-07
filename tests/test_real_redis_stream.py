import os
import time
import uuid
from urllib.parse import urlparse

import pytest
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from shared.message_contract import ChatMessage
from shared.redis_keys import (
    bots_key,
    context_key,
    dedup_key,
    messages_key,
    state_key,
    stats_key,
    stop_key,
)


pytestmark = pytest.mark.asyncio

REAL_REDIS_URL = os.getenv("REDIS_URL", "redis://101.133.133.237:6379/2")


def require_real_redis_tests() -> None:
    if os.getenv("RUN_REAL_REDIS_TESTS") != "1":
        pytest.skip("真实 Redis 测试默认跳过；设置 RUN_REAL_REDIS_TESTS=1 后执行")


def assert_redis_url_uses_db_2(redis_url: str) -> None:
    parsed = urlparse(redis_url)
    assert parsed.scheme == "redis"
    assert parsed.hostname == "101.133.133.237"
    assert parsed.port == 6379
    assert parsed.path == "/2"


@pytest.fixture
async def redis_client():
    require_real_redis_tests()
    assert_redis_url_uses_db_2(REAL_REDIS_URL)

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


@pytest.fixture
def test_match_id() -> str:
    return f"test_{uuid.uuid4().hex}"


def all_match_keys(match_id: str) -> list[str]:
    return [
        state_key(match_id),
        bots_key(match_id),
        messages_key(match_id),
        context_key(match_id),
        dedup_key(match_id),
        stop_key(match_id),
        stats_key(match_id),
    ]


async def cleanup_match_keys(redis_client: Redis, match_id: str) -> None:
    await redis_client.delete(*all_match_keys(match_id))


async def test_real_redis_can_ping(redis_client: Redis) -> None:
    assert await redis_client.ping() is True


async def test_real_redis_writes_state_hash(redis_client: Redis, test_match_id: str) -> None:
    try:
        key = state_key(test_match_id)

        await redis_client.hset(
            key,
            mapping={
                "status": "running",
                "bot_count": "3",
                "started_at": str(int(time.time())),
            },
        )

        state = await redis_client.hgetall(key)

        assert state["status"] == "running"
        assert state["bot_count"] == "3"
        assert state["started_at"].isdigit()
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_stream_accepts_chat_message(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        message = ChatMessage(
            match_id=test_match_id,
            bot_id="bot_001",
            bot_name="热血球迷1",
            content="这波进攻有点意思",
            match_time="第12分钟",
            event="测试事件",
            ts=int(time.time()),
        )

        message_id = await redis_client.xadd(
            messages_key(test_match_id),
            message.to_redis_fields(),
        )

        assert isinstance(message_id, str)
        assert await redis_client.xlen(messages_key(test_match_id)) == 1
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_stream_can_read_written_message(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        message = ChatMessage(
            match_id=test_match_id,
            bot_id="bot_001",
            bot_name="冷静分析1",
            content="现在节奏明显快起来了",
            match_time="第20分钟",
            event="测试事件",
            ts=int(time.time()),
        )

        await redis_client.xadd(messages_key(test_match_id), message.to_redis_fields())

        rows = await redis_client.xrange(messages_key(test_match_id), min="-", max="+")
        _, fields = rows[0]

        assert len(rows) == 1
        assert fields["match_id"] == test_match_id
        assert fields["bot_id"] == "bot_001"
        assert fields["bot_name"] == "冷静分析1"
        assert fields["content"] == "现在节奏明显快起来了"
        assert fields["match_time"] == "第20分钟"
        assert fields["event"] == "测试事件"
        assert fields["ts"].isdigit()
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_consumer_group_duplicate_create_returns_busygroup(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        stream = messages_key(test_match_id)
        group = "test-live-room"

        await redis_client.xadd(
            stream,
            {
                "match_id": test_match_id,
                "bot_id": "bot_001",
                "bot_name": "测试机器人",
                "content": "初始化 Stream",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )

        await redis_client.xgroup_create(name=stream, groupname=group, id="0")

        with pytest.raises(ResponseError, match="BUSYGROUP"):
            await redis_client.xgroup_create(name=stream, groupname=group, id="0")
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_consumer_group_can_read_and_ack(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        stream = messages_key(test_match_id)
        group = "test-live-room"
        consumer = "worker-1"

        await redis_client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        message_id = await redis_client.xadd(
            stream,
            {
                "match_id": test_match_id,
                "bot_id": "bot_001",
                "bot_name": "测试机器人",
                "content": "消费者组读取测试",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )

        rows = await redis_client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=1,
            block=1000,
        )

        assert rows
        assert rows[0][0] == stream
        assert rows[0][1][0][0] == message_id
        assert rows[0][1][0][1]["content"] == "消费者组读取测试"

        acked = await redis_client.xack(stream, group, message_id)

        assert acked == 1
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_xgroup_create_requires_mkstream_when_stream_missing(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        stream = messages_key(test_match_id)
        group = "test-live-room"

        with pytest.raises(ResponseError):
            await redis_client.xgroup_create(name=stream, groupname=group, id="0")

        assert await redis_client.exists(stream) == 0

        assert await redis_client.xgroup_create(
            name=stream,
            groupname=group,
            id="0",
            mkstream=True,
        )
        assert await redis_client.exists(stream) == 1
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_consumer_group_id_zero_replays_existing_messages(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        stream = messages_key(test_match_id)
        group = "test-live-room"
        consumer = "worker-1"

        old_message_id = await redis_client.xadd(
            stream,
            {
                "match_id": test_match_id,
                "bot_id": "bot_001",
                "bot_name": "测试机器人",
                "content": "消费者组创建前的历史消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )
        await redis_client.xgroup_create(name=stream, groupname=group, id="0")

        rows = await redis_client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=1,
            block=1000,
        )

        assert rows[0][1][0][0] == old_message_id
        assert rows[0][1][0][1]["content"] == "消费者组创建前的历史消息"
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_consumer_group_dollar_ignores_existing_messages(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        stream = messages_key(test_match_id)
        group = "test-live-room"
        consumer = "worker-1"

        await redis_client.xadd(
            stream,
            {
                "match_id": test_match_id,
                "bot_id": "bot_001",
                "bot_name": "测试机器人",
                "content": "消费者组创建前的历史消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )
        await redis_client.xgroup_create(name=stream, groupname=group, id="$")

        rows_before_new_message = await redis_client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=1,
            block=300,
        )

        assert rows_before_new_message == []

        new_message_id = await redis_client.xadd(
            stream,
            {
                "match_id": test_match_id,
                "bot_id": "bot_002",
                "bot_name": "测试机器人",
                "content": "消费者组创建后的新消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )
        rows_after_new_message = await redis_client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=1,
            block=1000,
        )

        assert rows_after_new_message[0][1][0][0] == new_message_id
        assert rows_after_new_message[0][1][0][1]["content"] == "消费者组创建后的新消息"
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_stream_can_trim_to_max_length(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    try:
        stream = messages_key(test_match_id)

        for index in range(5):
            await redis_client.xadd(
                stream,
                {
                    "match_id": test_match_id,
                    "bot_id": f"bot_{index}",
                    "bot_name": "测试机器人",
                    "content": f"第{index}条消息",
                    "match_time": "测试时间",
                    "event": "测试事件",
                    "ts": str(int(time.time())),
                },
                maxlen=2,
                approximate=False,
            )

        rows = await redis_client.xrange(stream, min="-", max="+")

        assert await redis_client.xlen(stream) == 2
        assert [fields["content"] for _, fields in rows] == ["第3条消息", "第4条消息"]
    finally:
        await cleanup_match_keys(redis_client, test_match_id)


async def test_real_redis_different_match_ids_are_isolated(redis_client: Redis) -> None:
    match_id_a = f"test_{uuid.uuid4().hex}"
    match_id_b = f"test_{uuid.uuid4().hex}"

    try:
        await redis_client.xadd(
            messages_key(match_id_a),
            {
                "match_id": match_id_a,
                "bot_id": "bot_001",
                "bot_name": "测试机器人A",
                "content": "A比赛消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )
        await redis_client.xadd(
            messages_key(match_id_b),
            {
                "match_id": match_id_b,
                "bot_id": "bot_001",
                "bot_name": "测试机器人B",
                "content": "B比赛消息",
                "match_time": "测试时间",
                "event": "测试事件",
                "ts": str(int(time.time())),
            },
        )

        assert await redis_client.xlen(messages_key(match_id_a)) == 1
        assert await redis_client.xlen(messages_key(match_id_b)) == 1
    finally:
        await cleanup_match_keys(redis_client, match_id_a)
        await cleanup_match_keys(redis_client, match_id_b)


async def test_real_redis_cleanup_removes_all_match_keys(
    redis_client: Redis,
    test_match_id: str,
) -> None:
    keys = all_match_keys(test_match_id)

    await redis_client.hset(state_key(test_match_id), mapping={"status": "running"})
    await redis_client.hset(bots_key(test_match_id), mapping={"bot_001": "热血球迷"})
    await redis_client.xadd(
        messages_key(test_match_id),
        {
            "match_id": test_match_id,
            "bot_id": "bot_001",
            "bot_name": "测试机器人",
            "content": "清理测试",
            "match_time": "测试时间",
            "event": "测试事件",
            "ts": str(int(time.time())),
        },
    )
    await redis_client.set(context_key(test_match_id), "{}")
    await redis_client.sadd(dedup_key(test_match_id), "hash_001")
    await redis_client.set(stop_key(test_match_id), "1")
    await redis_client.hset(stats_key(test_match_id), mapping={"sent_total": "1"})

    await cleanup_match_keys(redis_client, test_match_id)

    assert await redis_client.exists(*keys) == 0
