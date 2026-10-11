"""User Profile repository strictly scoped by user_id."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.profile import Education, Experience, Project, UserProfile


class ProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> Optional[UserProfile]:
        stmt = (
            select(UserProfile)
            .where(UserProfile.user_id == user_id)
            .options(
                selectinload(UserProfile.educations),
                selectinload(UserProfile.experiences),
                selectinload(UserProfile.projects),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(self, profile: UserProfile) -> UserProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def add_education(self, education: Education) -> Education:
        self.session.add(education)
        await self.session.flush()
        return education

    async def add_experience(self, experience: Experience) -> Experience:
        self.session.add(experience)
        await self.session.flush()
        return experience

    async def add_project(self, project: Project) -> Project:
        self.session.add(project)
        await self.session.flush()
        return project
