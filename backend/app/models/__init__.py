from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import side-effect: register models with Base.metadata
from app.models import (  # noqa: E402, F401
    fundamentals,
    news,
    options,
    pipeline,
    portfolio,
    recommendation,
    safety,
    screening,
    stocks,
)
