"""Email triage, scam signal evaluation, interview prep, and statistical analytics router."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from apps.api.models.user import User
from apps.api.repositories.fact_repository import FactRepository
from apps.api.repositories.job_repository import JobRepository
from apps.api.security.dependencies import get_current_user
from apps.api.services.analytics_service import AnalyticsService
from apps.api.services.email_triage_service import EmailTriageService
from apps.api.services.interview_prep_service import InterviewPrepService
from apps.api.services.scam_detection_service import ScamDetectionService

router = APIRouter(prefix="/api/v1", tags=["Triage & Analytics"])


@router.post(
    "/triage/email",
    summary="Upload and triage an inbound .eml recruiter email with intent classification",
)
async def triage_inbound_email(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".eml"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Inbound email must have .eml extension.",
        )

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB cap
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Email payload exceeds 5MB limit.",
        )

    parsed = EmailTriageService.parse_eml_content(content)
    classification = EmailTriageService.classify_email(
        subject=parsed["subject"],
        body=parsed["body"],
        sender=parsed["sender"],
    )

    return {
        "headers": {
            "subject": parsed["subject"],
            "sender": parsed["sender"],
            "date": parsed["date"],
        },
        "classification": classification,
        "message": "Email triaged. Suggested status updates require explicit user confirmation.",
    }


@router.post(
    "/jobs/{job_id}/scam-check",
    summary="Evaluate job listing for suspicious scam and predatory signals",
)
async def check_job_scam_signals(
    job_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    job_repo = JobRepository(session)
    job = await job_repo.get_by_id(current_user.id, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    result = ScamDetectionService.evaluate_job(
        title=job.title,
        company=job.company,
        description=job.description,
        salary_max=job.salary_max,
    )
    return result


@router.get(
    "/interview-prep/{job_id}",
    summary="Generate STAR-format interview prep questions strictly from verified profile facts",
)
async def get_interview_prep(
    job_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    job_repo = JobRepository(session)
    fact_repo = FactRepository(session)

    job = await job_repo.get_by_id(current_user.id, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    confirmed_facts = await fact_repo.list_by_user(current_user.id, confirmation_status="confirmed")
    if not confirmed_facts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate interview prep: Candidate has zero confirmed facts.",
        )

    kit = InterviewPrepService.generate_prep_kit(job, confirmed_facts)
    return kit


@router.get(
    "/analytics/funnel",
    summary="Fetch SQL-backed application funnel and Wilson score confidence intervals",
)
async def get_analytics_funnel(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = AnalyticsService(session)
    metrics = await svc.get_funnel_and_conversion_metrics(current_user.id)
    return metrics
