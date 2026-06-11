from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_settings
from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/settings")

_REC_TYPES = ("add_position", "sell_position", "sell_covered_call")


@router.get("")
async def get_settings_snapshot() -> dict:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        cost_mtd = await repo.llm_cost_month_to_date(datetime.now(tz=UTC).date())
    return {
        "approval_modes": {t: "manual" for t in _REC_TYPES},
        "auto_execution_enabled": False,
        "notifications": {
            "enabled": settings.notifications_enabled,
            "smtp_configured": settings.smtp_configured,
            "email_to": settings.notify_email_to,
        },
        "llm_model": settings.llm_model,
        "llm_cost_mtd": float(cost_mtd),
    }
