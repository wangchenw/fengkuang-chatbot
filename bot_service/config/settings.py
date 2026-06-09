from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    redis_url: str = "redis://127.0.0.1:6379/2"
    message_interval_seconds: float = 8.0  # 默认发言间隔
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model_id: str = ""

    nami_live_url: str = "http://115.190.176.164:1777/api/v5/football/match/live"
    nami_user: str = ""
    nami_secret: str = ""
    nami_poll_interval_seconds: float = 2.0
    match_redis_ttl_seconds: int = 86400
    match_context_ttl_seconds: int = 86400
    max_match_runtime_seconds: int = 14400  #避免一直持续生成弹幕，最多四个小时，假设上游开启了，但是没有关闭



    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


settings = Settings()
