from typing import Any

import httpx


class NamiLiveClient:
    def __init__(
        self,
        live_url: str,
        user: str,
        secret: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.live_url = live_url
        self.user = user
        self.secret = secret
        self.timeout_seconds = timeout_seconds

    async def fetch_live_matches(self) -> list[dict[str, Any]]:
        if not self.user or not self.secret:
            return []

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.live_url, params={"user": self.user, "secret": self.secret})
            response.raise_for_status()

        payload = response.json()
        results = payload.get("results", [])
        if not isinstance(results, list):
            return []

        return [item for item in results if isinstance(item, dict)]
