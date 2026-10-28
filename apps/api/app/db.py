"""Database engine, session factory and shared column types."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, TypeDecorator, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

_uuid7_lock = threading.Lock()
_uuid7_last = (0, 0)  # (unix ms, 12-bit counter)


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit unix-ms timestamp + 12-bit counter + random bits.

    Monotonic within the process (RFC 9562 section 6.2, method 1): ids created in the same
    millisecond increase, so ordering by id reproduces insertion order.
    """
    global _uuid7_last
    with _uuid7_lock:
        ts = int(time.time() * 1000) & ((1 << 48) - 1)
        last_ts, counter = _uuid7_last
        if ts <= last_ts:
            ts, counter = last_ts, counter + 1
            if counter > 0xFFF:  # counter exhausted: borrow the next millisecond
                ts, counter = ts + 1, 0
        else:
            counter = secrets.randbits(11)  # random start, leaving headroom to increment
        _uuid7_last = (ts, counter)
    rand_b = secrets.randbits(62)
    value = (ts << 80) | (0x7 << 76) | (counter << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetimes on every backend (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _configure_sqlite(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn: Any, _: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = get_settings().database_url
        _engine = create_async_engine(url, pool_pre_ping=True)
        if url.startswith("sqlite"):
            _configure_sqlite(_engine)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def reset_engine() -> None:
    """Dispose the engine (used by tests that swap DATABASE_URL)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
