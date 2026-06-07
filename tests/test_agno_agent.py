from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from bot_service.integrations.agno_agent import create_mimo_agent


def test_create_mimo_agent_returns_none_without_api_key() -> None:
    agent = create_mimo_agent(
        api_key="",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5",
    )

    assert agent is None


def test_create_mimo_agent_uses_agno_openai_like_model() -> None:
    agent = create_mimo_agent(
        api_key="test-key",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5",
    )

    assert isinstance(agent, Agent)
    assert isinstance(agent.model, OpenAILike)
    assert agent.model.id == "mimo-v2.5"
    assert agent.model.base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert agent.model.api_key == "test-key"
    assert agent.model.default_headers == {"api-key": "test-key"}
    assert agent.model.extra_body == {"thinking": {"type": "disabled"}}
