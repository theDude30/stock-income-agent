from app.pipeline.steps.base import Step, StepContext, StepFailure, StepResult
from app.pipeline.steps.dividends import DividendsStep
from app.pipeline.steps.fundamentals import FundamentalsStep
from app.pipeline.steps.news import NewsStep
from app.pipeline.steps.options import OptionsStep
from app.pipeline.steps.options_recommender import OptionsRecommenderStep
from app.pipeline.steps.prices import PricesStep
from app.pipeline.steps.recommender import RecommenderStep
from app.pipeline.steps.safety import SafetyStep
from app.pipeline.steps.screener import ScreenerStep
from app.pipeline.steps.universe import UniverseStep


def default_steps() -> list[Step]:
    return [
        UniverseStep(),
        PricesStep(),
        DividendsStep(),
        FundamentalsStep(),
        ScreenerStep(),
        OptionsStep(),
        NewsStep(),
        SafetyStep(),
        OptionsRecommenderStep(),
        RecommenderStep(),
    ]


__all__ = [
    "DividendsStep",
    "FundamentalsStep",
    "NewsStep",
    "OptionsRecommenderStep",
    "OptionsStep",
    "PricesStep",
    "RecommenderStep",
    "SafetyStep",
    "ScreenerStep",
    "Step",
    "StepContext",
    "StepFailure",
    "StepResult",
    "UniverseStep",
    "default_steps",
]
