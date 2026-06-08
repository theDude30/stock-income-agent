from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.llm.base import LLMClient
from app.pipeline.repo import PipelineRepo
from app.sources.base import Sources


class StepFailure(Exception):
    """Raised by a step when it fails at the step level (vs per-ticker failure)."""


@dataclass
class StepResult:
    """Returned by a successful step run. per_ticker_failures empty == clean run."""

    ok_count: int = 0
    per_ticker_failures: dict[str, str] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class StepContext:
    repo: PipelineRepo
    sources: Sources
    run_id: int
    now: Callable[[], datetime] = field(default=_utc_now)
    llm: LLMClient | None = None


class Step(ABC):
    """Base class for pipeline steps."""

    name: str = ""
    is_critical: bool = False

    def should_run(self, ctx: StepContext) -> bool:
        """Override to gate execution (e.g., universe runs only on the 1st of the month)."""
        return True

    @abstractmethod
    async def run(self, ctx: StepContext) -> StepResult: ...
