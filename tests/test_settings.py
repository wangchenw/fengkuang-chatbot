from bot_service.config.settings import Settings


def test_settings_use_local_redis_db_2_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.redis_url == "redis://127.0.0.1:6379/2"
    assert settings.message_interval_seconds == 8.0
    assert settings.llm_api_key == ""
    assert settings.llm_base_url == ""
    assert settings.llm_model_id == ""
    assert settings.match_redis_ttl_seconds == 86400
    assert settings.match_context_ttl_seconds == 86400


def test_settings_allow_env_override(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/9")

    settings = Settings(_env_file=None)

    assert settings.redis_url == "redis://localhost:6379/9"


def test_settings_accept_generic_llm_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL_ID", "provider-model")

    settings = Settings(_env_file=None)

    assert settings.llm_api_key == "llm-key"
    assert settings.llm_base_url == "https://provider.example/v1"
    assert settings.llm_model_id == "provider-model"
