import time
from typing import Any

from shared.message_contract import ChatMessage


def _clean_content(content: str) -> str:
    return content.strip().strip("\"'“”‘’").strip()


async def generate_llm_message(
    match_id: str,
    bot: dict[str, str],
    sequence: int,
    llm_agent: Any,
    now_ts: int | None = None,
) -> ChatMessage:
    prompt = (
        f"你是直播间观众，名字是{bot['name']}。\n"
        f"你的人设：{bot['persona']}。\n"
        f"比赛ID：{match_id}\n"
        f"发言序号：{sequence}\n"
        "当前还没有真实比赛上下文，请生成一句自然暖场弹幕。"
    )

    response = await llm_agent.arun(prompt, stream=False)
    content = getattr(response, "content", response)
    if not isinstance(content, str):
        content = str(content)

    return ChatMessage(
        match_id=match_id,
        bot_id=bot["bot_id"],
        bot_name=bot["name"],
        content=_clean_content(content),
        match_time="测试时间",
        event="测试事件",
        ts=now_ts if now_ts is not None else int(time.time()),
    )
