import pytest
from fakeredis.aioredis import FakeRedis

from bot_service.services.match_context_store import add_active_match, read_match_context
from bot_service.services.nami_live_poller import NamiLivePoller
from shared.redis_keys import active_matches_key, context_key, stats_key, stop_key


pytestmark = pytest.mark.asyncio


class FakeNamiClient:
    async def fetch_live_matches(self) -> list[dict[str, object]]:
        return [
            {
                "id": 4513032,
                "score": [4513032, 8, [1, 0, 0, 1, 6, 0, 0], [1, 0, 0, 2, 0, 0, 0], 0, ""],
                "stats": [],
                "incidents": [],
                "tlive": [],
            }
        ]


@pytest.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def test_run_once_stops_active_match_when_nami_match_is_finished(redis_client) -> None:
    await add_active_match(redis_client, "4513032")
    poller = NamiLivePoller(
        redis_client=redis_client,
        nami_client=FakeNamiClient(),
        poll_interval_seconds=2.0,
        context_ttl_seconds=86400,
        match_ttl_seconds=86400,
    )

    result = await poller.run_once()
    context = await read_match_context(redis_client, "4513032")

    assert result == {"active_count": 1, "updated_count": 1}
    assert context["score"][1] == 8
    assert await redis_client.get(stop_key("4513032")) == "1"
    assert await redis_client.smembers(active_matches_key()) == set()
    assert await redis_client.ttl(context_key("4513032")) == 86400
    assert await redis_client.ttl(stats_key("4513032")) == 86400
    assert await redis_client.ttl(stop_key("4513032")) == 86400
