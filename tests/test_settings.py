from bot_service.config.settings import Settings


def test_settings_use_real_redis_db_2_by_default() -> None:
    settings = Settings()

    assert settings.redis_url == "redis://101.133.133.237:6379/2"


def test_settings_allow_env_override(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/9")

    settings = Settings()

    assert settings.redis_url == "redis://localhost:6379/9"
