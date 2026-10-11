"""Profile facts router for managing, confirming, and rejecting atomic claims."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.schemas.fact import (
    ProfileFactCreate,
    ProfileFactResponse,
    ProfileFactUpdate,
)
from apps.api.security.dependencies import get_current_user
from apps.api.services.fact_service import FactService

router = APIRouter(prefix="/api/v1/facts", tags=["Profile Facts"])


@router.get("", response_model=List[ProfileFactResponse], summary="List atomic facts")
async def list_facts(
    status: Optional[str] = Query(None, description="Filter by candidate, confirmed, or rejected"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = FactService(session)
    return await service.list_facts(current_user.id, confirmation_status=status)


@router.post(
    "",
    response_model=ProfileFactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create atomic fact manually",
)
async def create_fact(
    payload: ProfileFactCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = FactService(session)
    return await service.create_fact(current_user.id, payload)


@router.patch("/{fact_id}", response_model=ProfileFactResponse, summary="Update atomic fact")
async def update_fact(
    fact_id: str,
    payload: ProfileFactUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = FactService(session)
    return await service.update_fact(current_user.id, fact_id, payload)


@router.post(
    "/{fact_id}/confirm",
    response_model=ProfileFactResponse,
    summary="Confirm atomic fact for generation and matching",
)
async def confirm_fact(
    fact_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = FactService(session)
    return await service.confirm_fact(current_user.id, fact_id)


@router.post(
    "/{fact_id}/reject",
    response_model=ProfileFactResponse,
    summary="Reject atomic fact from consideration",
)
async def reject_fact(
    fact_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = FactService(session)
    return await service.reject_fact(current_user.id, fact_id)


@router.delete(
    "/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete atomic fact",
)
async def delete_fact(
    fact_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = FactService(session)
    await service.delete_fact(current_user.id, fact_id)
