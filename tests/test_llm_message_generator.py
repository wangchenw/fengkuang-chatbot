from bot_service.personas.pool import get_personas
from bot_service.services.llm_message_generator import generate_llm_message
from shared.message_contract import ChatMessage


class FakeLlmClient:
    def __init__(self) -> None:
        self.messages = None

    async def generate_text(self, messages, max_completion_tokens=64, temperature=0.8) -> str:
        self.messages = messages
        return "这波进攻有点意思"


async def test_generate_llm_message_returns_chat_message() -> None:
    bot = get_personas(1)[0]
    llm_client = FakeLlmClient()

    message = await generate_llm_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        llm_client=llm_client,
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
    assert llm_client.messages[0]["role"] == "system"
    assert "情绪热烈" in llm_client.messages[0]["content"]


async def test_generate_llm_message_strips_quotes_and_whitespace() -> None:
    class QuotedClient:
        async def generate_text(self, messages, max_completion_tokens=64, temperature=0.8) -> str:
            return "  “这场看着挺刺激”  "

    bot = get_personas(1)[0]

    message = await generate_llm_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        llm_client=QuotedClient(),
        now_ts=1717660800,
    )

    assert message.content == "这场看着挺刺激"
