from bot_service.personas.pool import get_personas
from bot_service.services.llm_message_generator import (
    format_match_context_for_prompt,
    generate_llm_message,
)
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
    assert message.match_time == "实时"
    assert message.event == "live"
    assert message.ts == 1717660800
    assert llm_agent.kwargs["stream"] is False
    assert "match_001" in llm_agent.input
    assert "发言序号：" in llm_agent.input
    assert "我血压上来了" in llm_agent.input


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


def test_format_match_context_uses_nami_type_labels() -> None:
    context = {
        "score": [4513032, 6, [1, 0, 0, 1, 2, 0, 0], [1, 0, 0, 2, 3, 0, 0], 0, ""],
        "stats": [{"type": 5, "home": 2, "away": 1}],
        "incidents": [{"type": 19, "position": 0, "time": 45}],
        "tlive": [{"time": "", "type": 0, "data": "普通文字直播", "position": 0, "main": 0}],
    }

    prompt_context = format_match_context_for_prompt(context)

    assert "比赛状态：加时赛" in prompt_context
    assert "越位：主队2，客队1" in prompt_context
    assert "45分钟 中立伤停补时" in prompt_context
    assert "普通文字：普通文字直播" in prompt_context


def test_match_context_prompt_prioritizes_live_text_and_events_over_stats() -> None:
    context = {
        "score": [4513032, 4, [1, 0, 0, 1, 8, 0, 0], [1, 0, 0, 2, 0, 0, 0], 0, ""],
        "stats": [{"type": 2, "home": 8, "away": 0}],
        "incidents": [{"type": 3, "position": 2, "time": 90, "player_name": "测试球员"}],
        "tlive": [{"time": "90+1'", "type": 3, "data": "客队吃到黄牌", "position": 2, "main": 1}],
    }

    prompt_context = format_match_context_for_prompt(context)

    assert prompt_context.index("最新文字直播：") < prompt_context.index("最新重要事件：")
    assert prompt_context.index("最新重要事件：") < prompt_context.index("当前比分：")
    assert prompt_context.index("当前比分：") < prompt_context.index("背景统计：")


async def test_prompt_tells_llm_to_prefer_realtime_events_and_use_stats_sparingly() -> None:
    bot = get_personas(1)[0]
    llm_agent = FakeAgent()
    context = {
        "score": [4513032, 4, [1, 0, 0, 1, 8, 0, 0], [1, 0, 0, 2, 0, 0, 0], 0, ""],
        "stats": [{"type": 2, "home": 8, "away": 0}],
        "incidents": [{"type": 3, "position": 2, "time": 90, "player_name": "测试球员"}],
        "tlive": [{"time": "90+1'", "type": 3, "data": "客队吃到黄牌", "position": 2, "main": 1}],
    }

    await generate_llm_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        llm_agent=llm_agent,
        now_ts=1717660800,
        match_context=context,
    )

    assert "优先围绕最新文字直播或最新重要事件" in llm_agent.input
    assert "技术统计只能作为背景" in llm_agent.input
    assert "不要连续围绕角球、控球率、射正、危险进攻生成留言" in llm_agent.input


async def test_prompt_allows_noisy_live_room_language_without_real_abuse() -> None:
    bot = get_personas(1)[0]
    llm_agent = FakeAgent()

    await generate_llm_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        llm_agent=llm_agent,
        now_ts=1717660800,
        match_context={
            "score": [4513032, 4, [1, 0, 0, 1, 8, 0, 0], [1, 0, 0, 2, 0, 0, 0], 0, ""],
            "stats": [{"type": 2, "home": 8, "away": 0}],
            "incidents": [{"type": 1, "position": 1, "time": 90, "home_score": 2, "away_score": 1}],
            "tlive": [{"time": "90+1'", "type": 1, "data": "主队进球", "position": 1, "main": 1}],
        },
    )

    assert "大量感叹号、省略号、语气词" in llm_agent.input
    assert "可以质疑裁判、吐槽对方动作、阴阳怪气、跟风刷屏、偶尔跑题" in llm_agent.input
    assert "不要写仇恨、威胁、歧视、人身攻击或脏话堆叠" in llm_agent.input
