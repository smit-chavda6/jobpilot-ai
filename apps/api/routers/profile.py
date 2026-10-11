"""Profile thin router for fetching and editing candidate profile and experience."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.schemas.profile import (
    EducationCreate,
    EducationResponse,
    ExperienceCreate,
    ExperienceResponse,
    ProjectCreate,
    ProjectResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from apps.api.security.dependencies import get_current_user
from apps.api.services.profile_service import ProfileService

router = APIRouter(prefix="/api/v1/profile", tags=["Profile"])


@router.get("", response_model=UserProfileResponse, summary="Get candidate profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = ProfileService(session)
    return await service.get_profile(current_user.id)


@router.put("", response_model=UserProfileResponse, summary="Update candidate profile")
async def update_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = ProfileService(session)
    return await service.update_profile(current_user.id, payload)


@router.post(
    "/education",
    response_model=EducationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add education record",
)
async def add_education(
    payload: EducationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = ProfileService(session)
    edu = await service.add_education(current_user.id, payload)
    return EducationResponse.model_validate(edu)


@router.post(
    "/experience",
    response_model=ExperienceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add experience record",
)
async def add_experience(
    payload: ExperienceCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = ProfileService(session)
    exp = await service.add_experience(current_user.id, payload)
    return ExperienceResponse.model_validate(exp)


@router.post(
    "/project",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add project record",
)
async def add_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = ProfileService(session)
    proj = await service.add_project(current_user.id, payload)
    return ProjectResponse.model_validate(proj)
