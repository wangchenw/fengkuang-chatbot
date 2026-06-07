from bot_service.config.settings import Settings


def test_settings_use_local_redis_db_2_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.redis_url == "redis://127.0.0.1:6379/2"
    assert settings.message_interval_seconds == 8.0
    assert settings.mimo_model == "mimo-v2.5"
    assert settings.match_redis_ttl_seconds == 86400
    assert settings.match_context_ttl_seconds == 86400


def test_settings_allow_env_override(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/9")

    settings = Settings(_env_file=None)

    assert settings.redis_url == "redis://localhost:6379/9"
