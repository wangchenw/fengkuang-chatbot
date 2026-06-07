from bot_service.personas.pool import get_personas
from bot_service.services.llm_message_generator import generate_llm_message
from shared.message_contract import ChatMessage


class FakeAgentResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeAgent:
    def __init__(self) -> None:
        self.input = ""
        self.kwargs = {}

    async def arun(self, input, **kwargs) -> FakeAgentResponse:
        self.input = input
        self.kwargs = kwargs
        return FakeAgentResponse("这波进攻有点意思")


async def test_generate_llm_message_returns_chat_message() -> None:
    bot = get_personas(1)[0]
    llm_agent = FakeAgent()

    message = await generate_llm_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        llm_agent=llm_agent,
        now_ts=1717660800,
    )

    assert isinstance(message, ChatMessage)
    assert message.match_id == "match_001"
    assert message.bot_id == "bot_001"
    assert message.bot_name == bot["name"]
    assert message.content == "这波进攻有点意思"
    assert message.match_time == "测试时间"
    assert message.event == "测试事件"
    assert message.ts == 1717660800
    assert llm_agent.kwargs["stream"] is False
    assert "match_001" in llm_agent.input
    assert "发言序号：1" in llm_agent.input
    assert "情绪热烈" in llm_agent.input


async def test_generate_llm_message_strips_quotes_and_whitespace() -> None:
    class QuotedAgent:
        async def arun(self, input, **kwargs) -> FakeAgentResponse:
            return FakeAgentResponse("  “这场看着挺刺激”  ")

    bot = get_personas(1)[0]

    message = await generate_llm_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        llm_agent=QuotedAgent(),
        now_ts=1717660800,
    )

    assert message.content == "这场看着挺刺激"
