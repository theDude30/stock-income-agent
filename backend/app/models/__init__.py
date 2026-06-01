from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import side-effect: register models with Base.metadata
from app.models import news, options, pipeline, stocks  # noqa: E402, F401
