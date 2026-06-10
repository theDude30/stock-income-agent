from app.analysis.learning import (
    LESSON_MIN_SAMPLE,
    accept_lesson,
    is_duplicate,
    is_falsifiable,
    passes_sample_size_gate,
    survives_contradiction,
)


def test_sample_size_gate():
    assert passes_sample_size_gate(LESSON_MIN_SAMPLE) is True
    assert passes_sample_size_gate(LESSON_MIN_SAMPLE - 1) is False


def test_is_falsifiable():
    assert is_falsifiable("REITs with payout ratio above 95% cut within two quarters") is True
    assert is_falsifiable("be careful") is False          # banned phrase
    assert is_falsifiable("too short") is False           # under MIN_PATTERN_LEN
    assert is_falsifiable("   ") is False                 # empty after strip


def test_is_duplicate():
    active = ["High debt utilities cut dividends in rate-hike cycles consistently"]
    assert is_duplicate("high debt utilities cut dividends in rate hike cycles consistently", active) is True
    assert is_duplicate("Monthly payers with low FCF coverage tend to reduce distributions", active) is False


def test_survives_contradiction():
    assert survives_contradiction(8, 5) is True    # strictly greater
    assert survives_contradiction(5, 5) is False
    assert survives_contradiction(4, 5) is False


def test_accept_lesson():
    active = ["Existing lesson about something specific and falsifiable here"]
    assert accept_lesson(
        pattern="New falsifiable lesson with adequate descriptive length here",
        sample_size=5, active_patterns=active) is True
    assert accept_lesson(pattern="be careful", sample_size=9, active_patterns=active) is False
    assert accept_lesson(
        pattern="New falsifiable lesson with adequate descriptive length here",
        sample_size=3, active_patterns=active) is False
