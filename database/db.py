"""
Database connection and session management using SQLAlchemy Async Engine.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from config import settings

Base = declarative_base()

import json
from decimal import Decimal
from datetime import datetime

def _json_dumps(obj):
    def _default(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)
    return json.dumps(obj, default=_default)

# Configure SQLite async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    json_serializer=_json_dumps
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Initializes database schema."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncSession:
    """Provides an async session context."""
    async with AsyncSessionLocal() as session:
        yield session
