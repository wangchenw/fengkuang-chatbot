import asyncio

from fastapi import APIRouter, Depends, Query

from bot_service.config.settings import settings
from bot_service.integrations.redis_client import mimo_agent, redis_client
from bot_service.services.live_task_manager import LiveTaskManager


router = APIRouter()
_fake_loop_tasks: dict[str, asyncio.Task] = {}


def get_live_task_manager() -> LiveTaskManager:
    return LiveTaskManager(
        redis_client,
        llm_agent=mimo_agent,
        match_ttl_seconds=settings.match_redis_ttl_seconds,
        max_runtime_seconds=settings.max_match_runtime_seconds,
    )


def get_message_interval_seconds() -> float:
    return settings.message_interval_seconds


def ensure_fake_loop_running(
    match_id: str,
    manager: LiveTaskManager,
    interval_seconds: float,
) -> None:
    existing = _fake_loop_tasks.get(match_id)
    if existing and not existing.done():
        return

    task = asyncio.create_task(
        manager.run_fake_message_loop(
            match_id=match_id,
            interval_seconds=interval_seconds,
        )
    )
    _fake_loop_tasks[match_id] = task
    task.add_done_callback(lambda _: _fake_loop_tasks.pop(match_id, None))


async def cancel_fake_loop(match_id: str) -> None:
    task = _fake_loop_tasks.pop(match_id, None)
    if not task or task.done():
        return

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def cancel_all_fake_loops() -> None:
    match_ids = list(_fake_loop_tasks)
    for match_id in match_ids:
        await cancel_fake_loop(match_id)


@router.get("/startLive")
async def start_live(
    matchId: str,
    limit: int = Query(..., gt=0),
    manager: LiveTaskManager = Depends(get_live_task_manager),
    interval_seconds: float = Depends(get_message_interval_seconds),
) -> dict[str, object]:
    result = await manager.start_live(match_id=matchId, limit=limit)
    ensure_fake_loop_running(matchId, manager, interval_seconds)
    return result


@router.get("/stopLive")
async def stop_live(
    matchId: str,
    manager: LiveTaskManager = Depends(get_live_task_manager),
) -> dict[str, object]:
    result = await manager.stop_live(match_id=matchId)
    await cancel_fake_loop(matchId)
    return result


@router.get("/statusLive")
async def status_live(
    matchId: str,
    manager: LiveTaskManager = Depends(get_live_task_manager),
) -> dict[str, object]:
    return await manager.status_live(match_id=matchId)
