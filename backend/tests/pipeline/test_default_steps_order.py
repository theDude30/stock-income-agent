from app.pipeline.steps import default_steps


def test_default_steps_order():
    names = [s.name for s in default_steps()]
    assert names == [
        "universe", "prices", "dividends", "fundamentals", "screener",
        "options", "news", "safety", "options_recommender", "recommender",
        "executor", "income_tracker",
    ]
