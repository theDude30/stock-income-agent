from app.pipeline.steps.base import Step, StepContext, StepFailure, StepResult
from app.pipeline.steps.dividends import DividendsStep
from app.pipeline.steps.news import NewsStep
from app.pipeline.steps.options import OptionsStep
from app.pipeline.steps.prices import PricesStep
from app.pipeline.steps.universe import UniverseStep


def default_steps() -> list[Step]:
    return [
        UniverseStep(),
        PricesStep(),
        DividendsStep(),
        OptionsStep(),
        NewsStep(),
    ]


__all__ = [
    "DividendsStep",
    "NewsStep",
    "OptionsStep",
    "PricesStep",
    "Step",
    "StepContext",
    "StepFailure",
    "StepResult",
    "UniverseStep",
    "default_steps",
]
