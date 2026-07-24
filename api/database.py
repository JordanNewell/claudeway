"""
Claudeway Database

SQLAlchemy setup with async PostgreSQL support.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


async def init_db() -> None:
    """Initialize database - create tables.

    DEPRECATED: Database initialization is disabled since platform features
    (tenants, billing, templates) have been moved to platform-deprecated/.

    To re-enable: Move modules back from platform-deprecated/ and uncomment imports.
    """
    # Import models here to ensure they're registered
    # NOTE: All imports below are DEPRECATED - modules moved to platform-deprecated/
    # from platform_deprecated.tenants.models import Tenant
    # from agents.deployment import SwarmDeployment  # New name (was Agent)
    # from platform_deprecated.billing.models import UsageRecord, Invoice

    # Database initialization is disabled - no tables needed for core functionality
    pass

    # To re-enable database when platform features are restored:
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
