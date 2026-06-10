def test_new_models_registered():
    import app.models  # noqa: F401
    from app.models import Base

    tables = set(Base.metadata.tables)
    assert {"fundamentals", "screenings", "dividend_safety_scores", "recommendations"} <= tables
    assert {"positions", "trades", "income_events", "feedback"} <= tables  # add this line


def test_learning_models_registered():
    import app.models  # noqa: F401
    from app.models import Base
    tables = set(Base.metadata.tables)
    assert {"agent_lessons", "alerts"} <= tables
