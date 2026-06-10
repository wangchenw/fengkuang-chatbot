import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from bot_service.integrations.message_publisher import build_publisher
from bot_service.api.live import cancel_all_fake_loops, router as live_router
from bot_service.config.settings import settings
from bot_service.integrations.nami_client import NamiLiveClient
from bot_service.integrations.redis_client import redis_client
from bot_service.services.nami_live_poller import NamiLivePoller


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller_task: asyncio.Task | None = None

    if settings.nami_user and settings.nami_secret:
        nami_client = NamiLiveClient(
            live_url=settings.nami_live_url,
            user=settings.nami_user,
            secret=settings.nami_secret,
        )
        poller = NamiLivePoller(
            redis_client=redis_client,
            nami_client=nami_client,
            poll_interval_seconds=settings.nami_poll_interval_seconds,
            context_ttl_seconds=settings.match_redis_ttl_seconds,
            match_ttl_seconds=settings.match_redis_ttl_seconds,
        )
        poller_task = asyncio.create_task(poller.run_forever())

    app.state.publisher = await build_publisher(settings, redis_client)

    try:
        yield
    finally:
        if poller_task and not poller_task.done():
            poller_task.cancel()
            await asyncio.gather(poller_task, return_exceptions=True)
        await cancel_all_fake_loops()
        await app.state.publisher.close()


app = FastAPI(title="Livestream Bot Service", lifespan=lifespan)
app.include_router(live_router)
