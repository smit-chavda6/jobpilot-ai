"""Matching engine router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.repositories.job_repository import JobRepository
from apps.api.schemas.job import JobMatchResponse
from apps.api.security.dependencies import get_current_user
from apps.api.services.matching_service import MatchingService

router = APIRouter(prefix="/api/v1/jobs", tags=["Matching"])


@router.post(
    "/{job_id}/match",
    response_model=JobMatchResponse,
    summary="Compute or re-score match against confirmed profile facts",
)
async def compute_job_match(
    job_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = MatchingService(session)
    try:
        match = await service.compute_match(current_user.id, job_id)
        return JobMatchResponse.model_validate(match)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{job_id}/match",
    response_model=JobMatchResponse,
    summary="Get saved match score and explainable breakdown",
)
async def get_job_match(
    job_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = JobRepository(session)
    match = await repo.get_match(current_user.id, job_id)
    if not match:
        # Compute on the fly if not yet computed
        service = MatchingService(session)
        match = await service.compute_match(current_user.id, job_id)
    return JobMatchResponse.model_validate(match)
