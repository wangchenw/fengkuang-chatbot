from typing import Any

import httpx


class MimoClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._http_client = http_client
        self._owns_client = http_client is None

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        max_completion_tokens: int = 64,
        temperature: float = 0.8,
    ) -> str:
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_completion_tokens": max_completion_tokens,
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            content = self._extract_content(response.json())
            if not content:
                raise ValueError("MiMo returned empty content")
            return content
        finally:
            if self._owns_client:
                await client.aclose()

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        return str(message.get("content") or "").strip()


def create_mimo_client(
    api_key: str,
    base_url: str,
    model: str,
) -> MimoClient | None:
    if not api_key:
        return None

    return MimoClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
