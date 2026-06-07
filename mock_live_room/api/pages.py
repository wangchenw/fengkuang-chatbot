import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates

from bot_service.integrations.redis_client import redis_client
from mock_live_room.consumers.redis_stream_consumer import read_recent_messages


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def get_bot_service_url() -> str:
    return os.getenv("BOT_SERVICE_URL", "http://localhost:8000")


def get_redis_client() -> Any:
    return redis_client


async def call_bot_service(path: str, params: dict[str, object]) -> dict[str, object]:
    url = f"{get_bot_service_url()}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_match_id": "demo_001",
            "default_limit": 3,
        },
    )


@router.get("/room")
async def room(request: Request, matchId: str = Query(...)):
    return templates.TemplateResponse(
        request,
        "room.html",
        {
            "match_id": matchId,
        },
    )


@router.get("/api/start")
async def start_match(matchId: str, limit: int = Query(..., gt=0)) -> dict[str, object]:
    return await call_bot_service("/startLive", {"matchId": matchId, "limit": limit})


@router.get("/api/stop")
async def stop_match(matchId: str) -> dict[str, object]:
    return await call_bot_service("/stopLive", {"matchId": matchId})


@router.get("/api/messages")
async def messages(
    matchId: str,
    limit: int = Query(50, gt=0, le=200),
    redis=Depends(get_redis_client),
) -> dict[str, object]:
    return {
        "match_id": matchId,
        "messages": await read_recent_messages(redis, matchId, limit=limit),
    }
