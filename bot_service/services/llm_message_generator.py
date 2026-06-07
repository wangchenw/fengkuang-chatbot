import time
from typing import Any

from shared.message_contract import ChatMessage


def _clean_content(content: str) -> str:
    return content.strip().strip("\"'“”‘’").strip()


async def generate_llm_message(
    match_id: str,
    bot: dict[str, str],
    sequence: int,
    llm_client: Any,
    now_ts: int | None = None,
) -> ChatMessage:
    system_prompt = (
        f"你是直播间观众，名字是{bot['name']}。"
        f"你的人设：{bot['persona']}。"
        "请模拟真实直播间用户，只输出一句中文弹幕。"
        "要求：10到25个字，口语化，不要解释，不要加引号，不要带角色名前缀。"
    )
    user_prompt = (
        f"比赛ID：{match_id}\n"
        f"发言序号：{sequence}\n"
        "当前还没有真实比赛上下文，请生成一句自然暖场弹幕。"
    )

    content = await llm_client.generate_text(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=64,
        temperature=0.8,
    )

    return ChatMessage(
        match_id=match_id,
        bot_id=bot["bot_id"],
        bot_name=bot["name"],
        content=_clean_content(content),
        match_time="测试时间",
        event="测试事件",
        ts=now_ts if now_ts is not None else int(time.time()),
    )
