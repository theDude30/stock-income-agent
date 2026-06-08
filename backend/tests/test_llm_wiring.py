def test_make_llm_returns_client(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from app.api.pipeline import _make_llm

    llm = _make_llm()
    assert llm.model == "claude-sonnet-4-6"


def test_make_sources_includes_fundamentals(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    from app.api.pipeline import _make_sources

    assert _make_sources().fundamentals is not None
