from agno.agent import Agent
from agno.models.openai.like import OpenAILike


def create_llm_agent(
    api_key: str,
    base_url: str,
    model: str,
) -> Agent | None:
    if not api_key:
        return None

    return Agent(
        name="livestream-warmup-agent",
        model=OpenAILike(
            id=model,
            api_key=api_key,
            base_url=base_url,
            default_headers={"api-key": api_key},
            extra_body={"thinking": {"type": "disabled"}},
            max_completion_tokens=64,
            temperature=0.8,
        ),
        instructions=[
            "你负责为体育直播间生成自然中文暖场弹幕。",
            "只输出一句弹幕，不要解释，不要加引号，不要带角色名前缀。",
            "弹幕长度控制在10到25个中文字符左右，口语化。",
        ],
        markdown=False,
        telemetry=False,
    )
