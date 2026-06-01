from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(pg_container) -> AsyncGenerator[AsyncEngine, None]:
    url = pg_container.get_connection_url().replace("psycopg2", "asyncpg")
    eng = create_async_engine(url, echo=False, future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
