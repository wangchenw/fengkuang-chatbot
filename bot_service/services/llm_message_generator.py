import time
from typing import Any

from shared.message_contract import ChatMessage

STATUS_LABELS = {
    0: "异常",
    1: "未开赛",
    2: "上半场",
    3: "中场",
    4: "下半场",
    5: "加时赛",
    6: "加时赛",
    7: "点球决战",
    8: "完场",
    9: "推迟",
    10: "中断",
    11: "腰斩",
    12: "取消",
    13: "待定",
}

TYPE_LABELS = {
    0: "普通文字",
    1: "进球",
    2: "角球",
    3: "黄牌",
    4: "红牌",
    5: "越位",
    6: "任意球",
    7: "球门球",
    8: "点球",
    9: "换人",
    10: "比赛开始",
    11: "中场",
    12: "结束",
    13: "半场比分",
    15: "两黄变红",
    16: "点球未进",
    17: "乌龙球",
    18: "助攻",
    19: "伤停补时",
    21: "射正",
    22: "射偏",
    23: "进攻",
    24: "危险进攻",
    25: "控球率",
    26: "加时赛结束",
    27: "点球大战结束",
    28: "VAR",
    29: "点球大战点球",
    30: "点球大战点球未进",
    37: "射门被阻挡",
    38: "补水",
}


def _clean_content(content: str) -> str:
    return content.strip().strip("\"'“”‘’").strip()


def _usage_value(usage: Any, *names: str) -> int:
    for name in names:
        if isinstance(usage, dict) and name in usage:
            return int(usage[name] or 0)
        if hasattr(usage, name):
            return int(getattr(usage, name) or 0)
    return 0


def extract_token_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        usage = getattr(response, "metrics", None)
    if usage is None:
        return 0, 0

    input_tokens = _usage_value(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_value(usage, "output_tokens", "completion_tokens")
    return input_tokens, output_tokens


def _type_name(type_id: int) -> str:
    return TYPE_LABELS.get(type_id, f"类型{type_id}")


def _score_text(score: list) -> str:
    match_status = score[1]
    home = score[2]
    away = score[3]

    home_score = home[0]
    away_score = away[0]
    home_red = home[2]
    away_red = away[2]
    home_yellow = home[3]
    away_yellow = away[3]
    home_corner = home[4]
    away_corner = away[4]
    status_text = STATUS_LABELS[match_status]

    return (
        f"比赛状态：{status_text}；"
        f"比分：主队{home_score}-{away_score}客队；"
        f"红牌：主队{home_red}，客队{away_red}；"
        f"黄牌：主队{home_yellow}，客队{away_yellow}；"
        f"角球：主队{home_corner}，客队{away_corner}。"
    )


def _stats_text(stats: list | None) -> str:
    return "；".join(
        f"{_type_name(item['type'])}：主队{item['home']}，客队{item['away']}"
        for item in stats
    )


def _incidents_text(incidents: list[dict[str, Any]]) -> str:
    return "；".join(_incident_text(item) for item in incidents[-5:])


def _incident_text(item: dict[str, Any]) -> str:
    side = {0: "中立", 1: "主队", 2: "客队"}[item["position"]]
    text = f"{item['time']}分钟 {side}{_type_name(item['type'])}"

    if "player_name" in item:
        text += f" {item['player_name']}"

    if "home_score" in item and "away_score" in item:
        text += f" 比分{item['home_score']}-{item['away_score']}"

    return text


def _tlive_text(tlive: list[dict[str, Any]]) -> str:
    return "；".join(
        f"{item['time']}分钟 {_type_name(item['type'])}：{item['data']}"
        for item in tlive[-5:]
    )


def format_match_context_for_prompt(match_context: dict[str, Any] | None) -> str:
    if match_context is None:
        return ""

    return "\n".join(
        [
            f"最新文字直播：{_tlive_text(match_context['tlive'])}",
            f"最新重要事件：{_incidents_text(match_context['incidents'])}",
            f"当前比分：{_score_text(match_context['score'])}",
            f"背景统计：{_stats_text(match_context['stats'])}",
        ]
    )


def _build_prompt(
    match_id: str,
    bot: dict[str, str],
    sequence: int,
    match_context: dict[str, Any] | None = None,
) -> str:
    context_text = format_match_context_for_prompt(match_context)

    prompt = (
        f"你是直播间观众，名字是{bot['name']}。\n"
        f"你的人设：{bot['persona']}。\n"
        f"比赛ID：{match_id}\n"
        f"发言序号：{sequence}\n"
    )

    if context_text:
        prompt += (
            "当前比赛实时数据：\n"
            f"{context_text}\n"
            "请生成一句自然中文弹幕。优先围绕最新文字直播或最新重要事件做真实观众反应。"
            "如果最近动态是进球、红牌、点球、VAR、换人、中场或结束，优先回应这个动态。"
            "技术统计只能作为背景，最多偶尔参考；不要连续围绕角球、控球率、射正、危险进攻生成留言。"
            "语言要像真实足球直播间：大量感叹号、省略号、语气词，短句优先。"
            "可以质疑裁判、吐槽对方动作、阴阳怪气、跟风刷屏、偶尔跑题。"
            "可以用表情包文字，比如这球我不认、裁判你出来、主队加油啊我的老天、我血压上来了。"
            "不要每句都完整复述数据，不要像比赛报告。"
            "不要写仇恨、威胁、歧视、人身攻击或脏话堆叠。"
            "不要解释，不要加引号，不要带角色名前缀。"
            "不要编造数据里没有的球员名、队名或比分。"
        )
    else:
        prompt += (
            "当前还没有真实比赛上下文，请生成一句自然暖场弹幕。"
            "不要解释，不要加引号，不要带角色名前缀。"
        )

    return prompt


async def generate_llm_message_with_usage(
    match_id: str,
    bot: dict[str, str],
    sequence: int,
    llm_agent: Any,
    now_ts: int | None = None,
    match_context: dict[str, Any] | None = None,
) -> tuple[ChatMessage, tuple[int, int]]:
    prompt = _build_prompt(
        match_id=match_id,
        bot=bot,
        sequence=sequence,
        match_context=match_context,
    )
    response = await llm_agent.arun(prompt, stream=False)
    content = getattr(response, "content", response)
    if not isinstance(content, str):
        content = str(content)

    message = ChatMessage(
        match_id=match_id,
        bot_id=bot["bot_id"],
        bot_name=bot["name"],
        content=_clean_content(content),
        match_time="实时",
        event="live",
        ts=now_ts if now_ts is not None else int(time.time()),
    )
    return message, extract_token_usage(response)


async def generate_llm_message(
    match_id: str,
    bot: dict[str, str],
    sequence: int,
    llm_agent: Any,
    now_ts: int | None = None,
    match_context: dict[str, Any] | None = None,
) -> ChatMessage:
    message, _ = await generate_llm_message_with_usage(
        match_id=match_id,
        bot=bot,
        sequence=sequence,
        llm_agent=llm_agent,
        now_ts=now_ts,
        match_context=match_context,
    )
    return message
