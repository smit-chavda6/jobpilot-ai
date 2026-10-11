"""Application Tracker and Workflow API router."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.repositories.application_repository import ApplicationRepository
from apps.api.security.dependencies import get_current_user
from apps.api.services.application_workflow_service import (
    ApplicationWorkflowService,
    DuplicateApplicationError,
    HumanConfirmationRequiredError,
    StateTransitionError,
    UnapprovedPayloadError,
)

router = APIRouter(prefix="/api/v1/applications", tags=["Applications"])


class CreateApplicationRequest(BaseModel):
    job_id: str = Field(..., description="ID of job to apply for")
    notes: Optional[str] = Field(None, description="Optional application notes")


class UpdateApplicationPayloadRequest(BaseModel):
    resume_version_id: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None
    external_url: Optional[str] = None


class ApproveApplicationRequest(BaseModel):
    confirmed_by_user: bool = Field(
        ..., description="Explicit human-in-the-loop confirmation of submission package"
    )


class TransitionStatusRequest(BaseModel):
    target_status: str = Field(..., description="Desired next status in state machine")
    confirmed_by_user: bool = Field(
        False, description="Explicit confirmation if transitioning to submitted_confirmed"
    )
    notes: Optional[str] = Field(None, description="Optional notes for activity log")


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create new tracked application")
async def create_application(
    req: CreateApplicationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ApplicationWorkflowService(session)
    try:
        app = await svc.create_application(current_user.id, req.job_id, req.notes)
    except DuplicateApplicationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {
        "id": app.id,
        "job_id": app.job_id,
        "status": app.status,
        "notes": app.notes,
        "created_at": app.created_at,
    }


@router.get("", summary="List candidate tracked applications")
async def list_applications(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = ApplicationRepository(session)
    apps = await repo.list_by_user(current_user.id, status=status_filter)
    return [
        {
            "id": a.id,
            "job_id": a.job_id,
            "company": a.job.company if a.job else None,
            "title": a.job.title if a.job else None,
            "status": a.status,
            "applied_at": a.applied_at,
            "updated_at": a.updated_at,
            "activities_count": len(a.activities or []),
        }
        for a in apps
    ]


@router.get("/reminders", summary="Check follow-up reminders for submitted applications")
async def get_reminders(
    days: int = Query(7, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ApplicationWorkflowService(session)
    reminders = await svc.check_follow_up_reminders(current_user.id, days_threshold=days)
    return {"reminders": reminders, "count": len(reminders)}


@router.get("/{app_id}", summary="Get application details, materials, and audit activities")
async def get_application(
    app_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = ApplicationRepository(session)
    app = await repo.get_by_id(current_user.id, app_id)
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    svc = ApplicationWorkflowService(session)
    payload = svc.build_application_payload(app)
    approval = await svc.get_latest_approval(current_user.id, app.id)

    return {
        "id": app.id,
        "job_id": app.job_id,
        "status": app.status,
        "resume_version_id": app.resume_version_id,
        "cover_letter": app.cover_letter,
        "notes": app.notes,
        "applied_at": app.applied_at,
        "external_url": app.external_url,
        "is_approved": app.status == "approved" and approval is not None,
        "approval_hash": approval.payload_hash if approval else None,
        "payload": payload,
        "activities": [
            {
                "id": act.id,
                "from_status": act.from_status,
                "to_status": act.to_status,
                "activity_type": act.activity_type,
                "message": act.message,
                "created_at": act.created_at,
            }
            for act in (app.activities or [])
        ],
    }


@router.patch("/{app_id}", summary="Update application materials with automatic approval invalidation")
async def update_application_payload(
    app_id: str,
    req: UpdateApplicationPayloadRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ApplicationWorkflowService(session)
    try:
        app = await svc.update_payload(
            user_id=current_user.id,
            app_id=app_id,
            resume_version_id=req.resume_version_id,
            cover_letter=req.cover_letter,
            notes=req.notes,
            external_url=req.external_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "id": app.id,
        "status": app.status,
        "message": "Materials updated. Any existing approval has been invalidated if payload changed.",
    }


@router.post("/{app_id}/approve", summary="Cryptographically sign and approve submission package")
async def approve_application(
    app_id: str,
    req: ApproveApplicationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ApplicationWorkflowService(session)
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        app, approval = await svc.approve_application(
            user_id=current_user.id,
            app_id=app_id,
            confirmed_by_user=req.confirmed_by_user,
            ip_address=ip_addr,
            user_agent=user_agent,
        )
    except HumanConfirmationRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except StateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "id": app.id,
        "status": app.status,
        "approval_id": approval.id,
        "payload_hash": approval.payload_hash,
        "approved_at": approval.approved_at,
    }


@router.post("/{app_id}/transition", summary="Transition application state via state machine guards")
async def transition_application_status(
    app_id: str,
    req: TransitionStatusRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ApplicationWorkflowService(session)
    try:
        app = await svc.transition_status(
            user_id=current_user.id,
            app_id=app_id,
            target_status=req.target_status,
            confirmed_by_user=req.confirmed_by_user,
            notes=req.notes,
        )
    except HumanConfirmationRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UnapprovedPayloadError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except StateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "id": app.id,
        "status": app.status,
        "applied_at": app.applied_at,
        "message": f"Successfully transitioned to '{app.status}'.",
    }
