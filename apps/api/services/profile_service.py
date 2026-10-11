"""Candidate profile management service."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.profile import Education, Experience, Project, UserProfile
from apps.api.repositories.profile_repository import ProfileRepository
from apps.api.schemas.profile import (
    EducationCreate,
    ExperienceCreate,
    ProjectCreate,
    UserProfileResponse,
    UserProfileUpdate,
)


class ProfileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProfileRepository(session)

    async def get_profile(self, user_id: str) -> UserProfileResponse:
        profile = await self.repo.get_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found for current user.",
            )
        return UserProfileResponse.model_validate(profile)

    async def update_profile(self, user_id: str, data: UserProfileUpdate) -> UserProfileResponse:
        profile = await self.repo.get_by_user_id(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id, full_name="")
            self.session.add(profile)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(profile, key, value)

        await self.session.flush()
        return await self.get_profile(user_id)

    async def add_education(self, user_id: str, data: EducationCreate) -> Education:
        profile = await self.repo.get_by_user_id(user_id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        edu = Education(user_id=user_id, profile_id=profile.id, **data.model_dump())
        return await self.repo.add_education(edu)

    async def add_experience(self, user_id: str, data: ExperienceCreate) -> Experience:
        profile = await self.repo.get_by_user_id(user_id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        exp = Experience(user_id=user_id, profile_id=profile.id, **data.model_dump())
        return await self.repo.add_experience(exp)

    async def add_project(self, user_id: str, data: ProjectCreate) -> Project:
        profile = await self.repo.get_by_user_id(user_id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        proj = Project(user_id=user_id, profile_id=profile.id, **data.model_dump())
        return await self.repo.add_project(proj)
