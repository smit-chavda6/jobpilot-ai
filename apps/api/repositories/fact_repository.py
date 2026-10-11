"""ProfileFact repository scoped by user_id."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.fact import ProfileFact


class FactRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(
        self, user_id: str, confirmation_status: Optional[str] = None
    ) -> List[ProfileFact]:
        stmt = select(ProfileFact).where(ProfileFact.user_id == user_id)
        if confirmation_status:
            stmt = stmt.where(ProfileFact.confirmation_status == confirmation_status)
        stmt = stmt.order_by(ProfileFact.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, user_id: str, fact_id: str) -> Optional[ProfileFact]:
        """Returns fact strictly scoped to user_id to prevent IDOR leaks."""
        stmt = select(ProfileFact).where(ProfileFact.id == fact_id, ProfileFact.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, fact: ProfileFact) -> ProfileFact:
        self.session.add(fact)
        await self.session.flush()
        return fact

    async def delete(self, user_id: str, fact_id: str) -> bool:
        fact = await self.get_by_id(user_id, fact_id)
        if fact:
            await self.session.delete(fact)
            await self.session.flush()
            return True
        return False
