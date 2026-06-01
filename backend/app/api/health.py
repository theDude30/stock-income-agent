from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db import get_session_factory

router = APIRouter()


@router.get("/health")
async def health(response: Response) -> dict:
    factory = get_session_factory()
    db_status = "ok"
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"

    if db_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if db_status == "ok" else "degraded", "database": db_status}
