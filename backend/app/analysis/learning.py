"""Pure validation gates for Learner-proposed lessons. No DB, no network."""

LESSON_MIN_SAMPLE = 5
MIN_PATTERN_LEN = 20
BANNED_PHRASES = frozenset({"diversify", "be careful", "do more research"})
_DUP_OVERLAP_THRESHOLD = 0.8


def passes_sample_size_gate(sample_size: int) -> bool:
    return sample_size >= LESSON_MIN_SAMPLE


def is_falsifiable(pattern: str) -> bool:
    text = pattern.strip()
    if len(text) < MIN_PATTERN_LEN:
        return False
    return text.lower() not in BANNED_PHRASES


def _tokens(s: str) -> set[str]:
    return {t for t in s.lower().replace("-", " ").split() if t}


def is_duplicate(pattern: str, active_patterns: list[str]) -> bool:
    candidate = _tokens(pattern)
    if not candidate:
        return False
    for existing in active_patterns:
        other = _tokens(existing)
        if not other:
            continue
        overlap = len(candidate & other) / len(candidate | other)
        if overlap >= _DUP_OVERLAP_THRESHOLD:
            return True
    return False


def survives_contradiction(proposed_sample: int, active_sample: int) -> bool:
    return proposed_sample > active_sample


def accept_lesson(*, pattern: str, sample_size: int, active_patterns: list[str]) -> bool:
    return (
        passes_sample_size_gate(sample_size)
        and is_falsifiable(pattern)
        and not is_duplicate(pattern, active_patterns)
    )
