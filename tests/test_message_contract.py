from shared.message_contract import ChatMessage


def test_chat_message_generates_unique_message_id_by_default() -> None:
    first = ChatMessage(
        match_id="match_001",
        bot_id="bot_001",
        bot_name="热血球迷",
        content="这球看得我心跳加速",
        match_time="第68分钟",
        event="主队角球",
        ts=1717660800,
    )
    second = ChatMessage(
        match_id="match_001",
        bot_id="bot_001",
        bot_name="热血球迷",
        content="这球看得我心跳加速",
        match_time="第68分钟",
        event="主队角球",
        ts=1717660800,
    )

    assert first.message_id.startswith("msg_")
    assert second.message_id.startswith("msg_")
    assert first.message_id != second.message_id


def test_chat_message_keeps_contract_fields() -> None:
    message = ChatMessage(
        message_id="msg_test_001",
        match_id="match_001",
        bot_id="bot_001",
        bot_name="热血球迷",
        content="这球看得我心跳加速",
        match_time="第68分钟",
        event="主队角球",
        ts=1717660800,
    )

    assert message.message_id == "msg_test_001"
    assert message.match_id == "match_001"
    assert message.bot_id == "bot_001"
    assert message.bot_name == "热血球迷"
    assert message.content == "这球看得我心跳加速"
    assert message.match_time == "第68分钟"
    assert message.event == "主队角球"
    assert message.ts == 1717660800


def test_chat_message_converts_to_redis_stream_fields() -> None:
    message = ChatMessage(
        message_id="msg_test_001",
        match_id="match_001",
        bot_id="bot_001",
        bot_name="热血球迷",
        content="这球看得我心跳加速",
        match_time="第68分钟",
        event="主队角球",
        ts=1717660800,
    )

    fields = message.to_redis_fields()

    assert fields == {
        "message_id": "msg_test_001",
        "match_id": "match_001",
        "bot_id": "bot_001",
        "bot_name": "热血球迷",
        "content": "这球看得我心跳加速",
        "match_time": "第68分钟",
        "event": "主队角球",
        "ts": "1717660800",
    }
    assert all(isinstance(value, str) for value in fields.values())
