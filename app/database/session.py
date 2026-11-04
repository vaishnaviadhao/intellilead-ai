from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import DatabaseSettings


def build_engine(settings: DatabaseSettings):
    return create_async_engine(settings.database_url, echo=settings.sql_echo, pool_pre_ping=True)


def build_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def tenant_session(session_factory, organization_id: UUID):
    """Open a transaction with PostgreSQL RLS tenant context set transaction-locally."""
    async with session_factory() as session:
        async with session.begin():
            if session.bind.dialect.name == "postgresql":
                await session.execute(
                    text("SELECT set_config('app.current_organization_id', :org_id, true)"),
                    {"org_id": str(organization_id)},
                )
            yield session
