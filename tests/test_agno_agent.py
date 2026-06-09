from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from bot_service.integrations.agno_agent import create_llm_agent


def test_create_llm_agent_returns_none_without_api_key() -> None:
    agent = create_llm_agent(
        api_key="",
        base_url="https://provider.example/v1",
        model="provider-model",
    )

    assert agent is None


def test_create_llm_agent_uses_agno_openai_like_model() -> None:
    agent = create_llm_agent(
        api_key="test-key",
        base_url="https://provider.example/v1",
        model="provider-model",
    )

    assert isinstance(agent, Agent)
    assert isinstance(agent.model, OpenAILike)
    assert agent.model.id == "provider-model"
    assert agent.model.base_url == "https://provider.example/v1"
    assert agent.model.api_key == "test-key"
    assert agent.model.default_headers == {"api-key": "test-key"}
    assert agent.model.extra_body == {"thinking": {"type": "disabled"}}
