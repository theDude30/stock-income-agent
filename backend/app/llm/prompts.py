import json

SAFETY_PROMPT_VERSION = "safety-v1"

SAFETY_SYSTEM = (
    "You are a conservative dividend safety analyst. Given fundamentals, recent "
    "dividend history, and news for a single stock, assess the likelihood that the "
    "company sustains (and ideally grows) its dividend over the next 12 months. "
    "Be skeptical: weight payout ratio, free-cash-flow coverage, leverage, and any "
    "deteriorating news heavily. Return a calibrated score from 0 (imminent cut risk) "
    "to 100 (rock-solid)."
)


def build_safety_prompt(
    *, ticker: str, metrics: dict, recent_dividends: list[str],
    recent_news: list[str], active_lessons: list[str],
) -> str:
    lessons_block = "\n".join(f"- {x}" for x in active_lessons) or "(none yet)"
    news_block = "\n".join(f"- {x}" for x in recent_news) or "(no recent news)"
    divs_block = "\n".join(f"- {x}" for x in recent_dividends) or "(no recent dividends)"
    return (
        f"Ticker: {ticker}\n\n"
        f"Computed safety metrics:\n{json.dumps(metrics, indent=2, default=str)}\n\n"
        f"Recent dividend declarations:\n{divs_block}\n\n"
        f"Recent news headlines:\n{news_block}\n\n"
        f"Active learned lessons (apply if relevant):\n{lessons_block}\n"
    )


OPTIONS_PROMPT_VERSION = "options-v1"

OPTIONS_SYSTEM = (
    "You are an options income analyst. Given a holding's price and a short list of "
    "pre-scored out-of-the-money call candidates, pick the single best covered call to "
    "sell: maximize premium income while keeping the probability of assignment modest. "
    "Prefer 30-45 days to expiration."
)


def build_options_prompt(*, ticker: str, price: float, candidates: list[dict]) -> str:
    return (
        f"Ticker: {ticker}\nCurrent price: {price}\n\n"
        f"Candidate calls (pre-scored):\n{json.dumps(candidates, indent=2, default=str)}\n\n"
        "Pick the best one and explain why."
    )


LEARNER_PROMPT_VERSION = "learner-v1"

LEARNER_SYSTEM = (
    "You are a portfolio post-mortem analyst for a dividend + covered-call income agent. "
    "Review the past week's closed-position outcomes, income, dividend-safety changes, and "
    "user-rejected recommendations. Propose only falsifiable, evidence-backed lessons with a "
    "sample size of at least 5 closed positions. Flag any proposal that contradicts an active "
    "lesson by setting contradicts_lesson_id. Propose retirements for active lessons the "
    "evidence no longer supports. Do not propose vague advice like 'diversify' or 'be careful'."
)


def build_learner_prompt(*, active_lessons: list[str], feedback: list[dict],
                         income_events: list[dict], safety_deltas: list[dict],
                         rejections: list[dict]) -> str:
    lessons_block = "\n".join(f"- {x}" for x in active_lessons) or "(none yet)"
    return (
        f"Active lessons (propose retirements by id if unsupported):\n{lessons_block}\n\n"
        f"Closed-position feedback:\n{json.dumps(feedback, indent=2, default=str)}\n\n"
        f"Income events:\n{json.dumps(income_events, indent=2, default=str)}\n\n"
        f"Dividend-safety score changes:\n{json.dumps(safety_deltas, indent=2, default=str)}\n\n"
        f"User-rejected recommendations:\n{json.dumps(rejections, indent=2, default=str)}\n\n"
        "Propose new_lessons (each with pattern, sample_size, evidence_recommendation_ids, "
        "optional contradicts_lesson_id) and retirements (lesson_id + reason)."
    )
