import pytest
from pydantic import ValidationError


def test_settings_loads_postgres_url_from_components(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("APP_ENV", "test")

    s = Settings()
    assert s.postgres_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.app_env == "test"


def test_settings_requires_postgres_password(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("APP_ENV", "test")

    with pytest.raises(ValidationError):
        Settings()


def test_llm_model_default(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    from app.config import Settings

    assert Settings().llm_model == "claude-sonnet-4-6"


def test_treasury_1m_yield_default(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.delenv("TREASURY_1M_YIELD_PCT", raising=False)

    from app.config import Settings

    assert Settings().treasury_1m_yield_pct == 4.2


def test_treasury_1m_yield_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("TREASURY_1M_YIELD_PCT", "5.1")

    from app.config import Settings

    assert Settings().treasury_1m_yield_pct == 5.1
