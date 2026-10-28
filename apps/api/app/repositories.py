"""User-scoped data access. Every query against a user-owned table goes through `Repo`,
which always adds `WHERE user_id = :current_user`. Cross-tenant reads therefore return
404 (NotFound) rather than leaking existence.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression

from app.db import Base
from app.errors import NotFound, UnprocessableError


class Repo[M: Base]:
    def __init__(self, session: AsyncSession, model: type[M], user_id: uuid.UUID):
        self.session = session
        self.model = model
        self.user_id = user_id

    def query(self) -> Select[tuple[M]]:
        return select(self.model).where(self.model.user_id == self.user_id)  # type: ignore[attr-defined]

    async def get(self, obj_id: uuid.UUID) -> M:
        row = (await self.session.execute(self.query().where(self.model.id == obj_id))).scalar_one_or_none()
        if row is None:
            raise NotFound(f"{self.model.__name__} not found")
        return row

    async def find(self, *where: Any) -> M | None:
        return (await self.session.execute(self.query().where(*where))).scalars().first()

    async def list(self, *where: Any, order_by: Any = None, limit: int | None = None) -> list[M]:
        q = self.query().where(*where)
        if order_by is not None:
            # Rows created in one transaction share created_at; the time-ordered UUIDv7 id breaks ties
            # deterministically (insertion order) on every database.
            desc = isinstance(order_by, UnaryExpression) and order_by.modifier is operators.desc_op
            pk = self.model.id
            q = q.order_by(order_by, pk.desc() if desc else pk)
        if limit:
            q = q.limit(limit)
        return list((await self.session.execute(q)).scalars().all())

    async def count(self, *where: Any) -> int:
        owner = self.model.user_id == self.user_id  # type: ignore[attr-defined]
        q = select(func.count()).select_from(self.model).where(owner, *where)
        return int((await self.session.execute(q)).scalar_one())

    def add(self, **fields: Any) -> M:
        obj = self.model(user_id=self.user_id, **fields)
        self.session.add(obj)
        return obj

    async def delete(self, obj: M) -> None:
        await self.session.delete(obj)

    async def delete_all(self) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.user_id == self.user_id)  # type: ignore[attr-defined]
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------- cursor pagination


def encode_cursor(created_at: datetime, obj_id: uuid.UUID) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "i": str(obj_id)})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(raw["t"]), uuid.UUID(raw["i"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise UnprocessableError("Invalid cursor", code="invalid_cursor") from exc


async def paginate[M: Base](
    session: AsyncSession, q: Select[tuple[M]], model: type[M], cursor: str | None, limit: int
) -> tuple[list[M], str | None]:
    """Newest-first keyset pagination on (created_at, id)."""
    if cursor:
        t, i = decode_cursor(cursor)
        q = q.where(or_(model.created_at < t, and_(model.created_at == t, model.id < i)))
    q = q.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    rows = list((await session.execute(q)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id)
    return rows, next_cursor
