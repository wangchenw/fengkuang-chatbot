import json

import httpx
import pytest

from bot_service.integrations.mimo_client import MimoClient


pytestmark = pytest.mark.asyncio


async def test_mimo_client_calls_openai_compatible_chat_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)

        assert str(request.url) == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
        assert request.headers["api-key"] == "test-key"
        assert body["model"] == "mimo-v2.5-pro"
        assert body["messages"] == [{"role": "user", "content": "说一句弹幕"}]
        assert body["max_completion_tokens"] == 64
        assert body["temperature"] == 0.8

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "这波进攻有点意思",
                        },
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MimoClient(
            api_key="test-key",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            model="mimo-v2.5-pro",
            http_client=http_client,
        )

        content = await client.generate_text(
            messages=[{"role": "user", "content": "说一句弹幕"}],
            max_completion_tokens=64,
            temperature=0.8,
        )

    assert content == "这波进攻有点意思"


async def test_mimo_client_rejects_empty_response_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MimoClient(
            api_key="test-key",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            model="mimo-v2.5-pro",
            http_client=http_client,
        )

        with pytest.raises(ValueError, match="empty content"):
            await client.generate_text(messages=[{"role": "user", "content": "说一句弹幕"}])
