import time

from shared.message_contract import ChatMessage


FAKE_MESSAGES = [
    "这比赛节奏起来了",
    "这波进攻有点意思",
    "感觉马上要出机会了",
    "这个角球得好好把握",
    "主队现在压得挺靠前",
    "客队反击速度不慢啊",
    "这场看着挺刺激",
    "中场这个调度很关键",
]


def generate_fake_message(
    match_id: str,
    bot: dict[str, str],
    sequence: int,
    now_ts: int | None = None,
) -> ChatMessage:
    content = FAKE_MESSAGES[sequence % len(FAKE_MESSAGES)]

    return ChatMessage(
        match_id=match_id,
        bot_id=bot["bot_id"],
        bot_name=bot["name"],
        content=content,
        match_time="测试时间",
        event="测试事件",
        ts=now_ts if now_ts is not None else int(time.time()),
    )
