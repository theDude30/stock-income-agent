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
