"""ProfileFact service managing atomic verifiable claims."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.fact import ProfileFact
from apps.api.repositories.fact_repository import FactRepository
from apps.api.schemas.fact import (
    ProfileFactCreate,
    ProfileFactResponse,
    ProfileFactUpdate,
)


class FactService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = FactRepository(session)

    async def list_facts(
        self, user_id: str, confirmation_status: Optional[str] = None
    ) -> List[ProfileFactResponse]:
        facts = await self.repo.list_by_user(user_id, confirmation_status)
        return [ProfileFactResponse.model_validate(f) for f in facts]

    async def create_fact(self, user_id: str, data: ProfileFactCreate) -> ProfileFactResponse:
        # User-manually entered facts default to 'confirmed' status
        status_val = "confirmed" if data.source_type == "manual" else "candidate"
        fact = ProfileFact(
            user_id=user_id,
            text=data.text,
            category=data.category,
            source_type=data.source_type,
            source_id=data.source_id,
            confirmation_status=status_val,
            entities=data.entities,
        )
        created = await self.repo.create(fact)
        return ProfileFactResponse.model_validate(created)

    async def update_fact(
        self, user_id: str, fact_id: str, data: ProfileFactUpdate
    ) -> ProfileFactResponse:
        fact = await self.repo.get_by_id(user_id, fact_id)
        if not fact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fact not found or access denied.",
            )

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(fact, key, value)

        await self.session.flush()
        return ProfileFactResponse.model_validate(fact)

    async def confirm_fact(self, user_id: str, fact_id: str) -> ProfileFactResponse:
        return await self.update_fact(
            user_id, fact_id, ProfileFactUpdate(confirmation_status="confirmed")
        )

    async def reject_fact(self, user_id: str, fact_id: str) -> ProfileFactResponse:
        return await self.update_fact(
            user_id, fact_id, ProfileFactUpdate(confirmation_status="rejected")
        )

    async def delete_fact(self, user_id: str, fact_id: str) -> None:
        deleted = await self.repo.delete(user_id, fact_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fact not found or access denied.",
            )
