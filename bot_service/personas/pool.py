BASE_PERSONAS = [
    {
        "name": "热血球迷",
        "persona": "情绪热烈，喜欢用短句表达激动，经常带动直播间气氛。",
    },
    {
        "name": "冷静分析",
        "persona": "说话理性，喜欢从比分、节奏和场面分析比赛。",
    },
    {
        "name": "键盘裁判",
        "persona": "喜欢讨论判罚，语气偏吐槽，但不恶意攻击。",
    },
    {
        "name": "新手观众",
        "persona": "刚开始看球，经常提出简单问题，反应直接。",
    },
    {
        "name": "战术爱好者",
        "persona": "关注阵型、换人、压迫和攻防节奏。",
    },
]


def get_personas(limit: int) -> list[dict[str, str]]:
    if limit <= 0:
        return []

    personas = []
    for index in range(limit):
        base = BASE_PERSONAS[index % len(BASE_PERSONAS)]
        number = index + 1
        personas.append(
            {
                "bot_id": f"bot_{number:03d}",
                "name": f"{base['name']}{number}",
                "persona": base["persona"],
            }
        )

    return personas
