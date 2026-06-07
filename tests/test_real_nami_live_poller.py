import os

import pytest
from fakeredis.aioredis import FakeRedis

from bot_service.config.settings import Settings
from bot_service.integrations.nami_client import NamiLiveClient
from bot_service.services.match_context_store import add_active_match, read_match_context
from bot_service.services.nami_live_poller import NamiLivePoller


pytestmark = pytest.mark.asyncio

LIVE_STATUSES = {2, 3, 4, 5, 7}


def require_real_nami_tests(settings: Settings) -> None:
    if os.getenv("RUN_REAL_NAMI_TESTS") != "1":
        pytest.skip("Nami 真实接口测试默认跳过；设置 RUN_REAL_NAMI_TESTS=1 后执行")
    if not settings.nami_user or not settings.nami_secret:
        pytest.skip("缺少 Nami 接口配置")


async def test_real_nami_poller_uses_current_live_match_id() -> None:
    settings = Settings()
    require_real_nami_tests(settings)

    nami_client = NamiLiveClient(
        live_url=settings.nami_live_url,
        user=settings.nami_user,
        secret=settings.nami_secret,
    )
    matches = await nami_client.fetch_live_matches()
    live_matches = [match for match in matches if match["score"][1] in LIVE_STATUSES]
    if not live_matches:
        pytest.skip("当前纳米接口没有进行中的比赛")

    match_id = str(live_matches[0]["id"])
    redis_client = FakeRedis(decode_responses=True)
    try:
        await add_active_match(redis_client, match_id)
        poller = NamiLivePoller(
            redis_client=redis_client,
            nami_client=nami_client,
            poll_interval_seconds=2.0,
            context_ttl_seconds=settings.match_redis_ttl_seconds,
            match_ttl_seconds=settings.match_redis_ttl_seconds,
        )

        result = await poller.run_once()
        context = await read_match_context(redis_client, match_id)

        assert result["active_count"] == 1
        assert result["updated_count"] == 1
        assert context is not None
        assert context["source"] == "nami"
        assert context["match_id"] == match_id
        assert context["score"][0] == int(match_id)
        assert context["score"][1] in LIVE_STATUSES
    finally:
        await redis_client.aclose()
