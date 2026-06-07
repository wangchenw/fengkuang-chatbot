from bot_service.personas.pool import get_personas
from bot_service.services.fake_message_generator import generate_fake_message
from shared.message_contract import ChatMessage


def test_generate_fake_message_returns_chat_message() -> None:
    bot = get_personas(1)[0]

    message = generate_fake_message(
        match_id="match_001",
        bot=bot,
        sequence=1,
        now_ts=1717660800,
    )

    assert isinstance(message, ChatMessage)
    assert message.match_id == "match_001"
    assert message.bot_id == "bot_001"
    assert message.bot_name == bot["name"]
    assert message.content
    assert message.match_time == "测试时间"
    assert message.event == "测试事件"
    assert message.ts == 1717660800


def test_generate_fake_message_rotates_fixed_content_by_sequence() -> None:
    bot = get_personas(1)[0]

    first = generate_fake_message("match_001", bot, sequence=0, now_ts=1717660800)
    second = generate_fake_message("match_001", bot, sequence=1, now_ts=1717660800)

    assert first.content != second.content


def test_generate_fake_message_can_convert_to_redis_fields() -> None:
    bot = get_personas(1)[0]

    message = generate_fake_message(
        match_id="match_001",
        bot=bot,
        sequence=0,
        now_ts=1717660800,
    )

    fields = message.to_redis_fields()

    assert fields["match_id"] == "match_001"
    assert fields["bot_id"] == "bot_001"
    assert fields["ts"] == "1717660800"
    assert all(isinstance(value, str) for value in fields.values())
