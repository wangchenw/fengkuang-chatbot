import asyncio
import sys
import time
from urllib.parse import urlparse

from bot_service.config.settings import settings
from bot_service.integrations.redis_client import create_redis_client, redis_client


async def test_client(name: str, client) -> bool:
    try:
        t0 = time.perf_counter()
        pong = await client.ping()
        ping_ms = int((time.perf_counter() - t0) * 1000)

        key = "live:healthcheck:probe"
        await client.set(key, "ok", ex=30)
        val = await client.get(key)
        await client.delete(key)

        info = await client.info(section="server")
        version = info.get("redis_version", "unknown")
        print(
            f"[{name}] OK ping={pong} latency={ping_ms}ms "
            f"set/get={val} redis_version={version}"
        )
        return True
    except Exception as exc:
        print(f"[{name}] FAIL {type(exc).__name__}: {exc}")
        return False
    finally:
        await client.aclose()


async def test_singleton() -> bool:
    try:
        t0 = time.perf_counter()
        pong = await redis_client.ping()
        ping_ms = int((time.perf_counter() - t0) * 1000)
        print(f"[singleton] OK ping={pong} latency={ping_ms}ms")
        return True
    except Exception as exc:
        print(f"[singleton] FAIL {type(exc).__name__}: {exc}")
        return False


async def main() -> int:
    parsed = urlparse(settings.redis_url)
    db = parsed.path.lstrip("/") or "0"
    print(
        f"target={parsed.hostname}:{parsed.port} db={db} "
        f"auth={'yes' if parsed.password else 'no'}"
    )

    ok_new = await test_client("new_client", create_redis_client(settings.redis_url))
    ok_singleton = await test_singleton()
    return 0 if ok_new and ok_singleton else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
