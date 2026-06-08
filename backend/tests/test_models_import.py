def test_new_models_registered():
    from app.models import Base
    import app.models  # noqa: F401

    tables = set(Base.metadata.tables)
    assert {"fundamentals", "screenings", "dividend_safety_scores", "recommendations"} <= tables
